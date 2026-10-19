"""The job worker: runs the queued jobs of an application until it is stopped.

A worker launches DBOS, which starts again, from the beginning of their activity, the
jobs this worker (same ``worker_id`` and version, see :func:`engine_version`) was
running when it stopped, then takes queued jobs. Jobs interrupted under another
version are not started again (their code may have changed): the worker records them
as failed, to be retried, and cancels them in the engine. Stop the workers of a
release before starting those of the next one.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import uuid
from datetime import UTC, datetime
from importlib.metadata import version as package_version
from typing import TYPE_CHECKING

from dbos import DBOS, DBOSConfig

from brevia.config.settings import BreviaSettings
from brevia.errors import InternalError
from brevia.jobs import workflow
from brevia.jobs.backend import (
    APP_NAME,
    CLEANUP,
    QUEUE,
    DbosBackend,
    guard_engine_logs,
)
from brevia.jobs.runtime import JobRuntime

if TYPE_CHECKING:
    from brevia.runs.application import Brevia

logger = logging.getLogger(__name__)

CLEANUP_SCHEDULE = "0 3 * * *"
"""Daily cleanup of expired data, at 03:00 UTC."""


def launch(app: Brevia, backend: DbosBackend, version: str, worker_id: str) -> None:
    """Launch DBOS in this process to run the jobs of ``app``."""
    workflow.install(_runtime(app), version)
    config: DBOSConfig = {
        "name": APP_NAME,
        "system_database_url": backend.url.get_secret_value(),
        "dbos_system_schema": backend.schema,
        "application_version": version,
        "executor_id": worker_id,
        # Migrated by `brevia db upgrade`, never by a worker.
        "run_migrations": False,
    }
    DBOS(config=config)
    # After the engine has added its console handler, which this replaces.
    guard_engine_logs()
    DBOS.launch()
    # DBOS gives new jobs only to workers of the latest registered version, and
    # starting an earlier version does not make it the latest again: without this,
    # after a rollback new jobs would stay queued until a later worker returned.
    # The warning of DBOS at launch that this version is not the latest is then
    # out of date.
    DBOS.set_latest_application_version(version)


def engine_version(settings: BreviaSettings) -> str:
    """Version the engine runs the jobs under: ``BREVIA_APP_VERSION``, or the version
    of Brevia when it is not set.

    Interrupted jobs start again only under the same version. The code that the
    engine resumes is the workflow of Brevia, which changes only with Brevia; a
    change of an activity is caught by its own version, checked when a job starts.
    """
    return settings.app_version or f"brevia-{package_version('brevia')}"


def _runtime(app: Brevia) -> JobRuntime:
    """What the jobs use of ``app``: the only part of it the worker reads."""
    runtime = app._job_runtime
    if runtime is None:
        raise RuntimeError("The worker needs the job backend of the settings")
    return runtime


async def fail_other_versions(app: Brevia, backend: DbosBackend, version: str) -> int:
    """Record as failed, and cancel, the jobs interrupted under another version."""
    stale = [
        (run_id, other) for run_id, other in await backend.pending() if other != version
    ]
    for run_id, other in stale:
        # Recorded first: a reader that saw the engine cancelled before this record
        # would report a cancellation. Both writes are repeated on the next start.
        error = InternalError(
            "The job was interrupted by a release of the application: retry it",
            {"app_version": other},
            retryable=True,
        )
        await _runtime(app).store.finish_job(
            uuid.UUID(run_id), "failed", None, error.to_dict(), datetime.now(UTC)
        )
        await backend.cancel(run_id)
        logger.warning(
            "Job of version %s failed: interrupted by a release",
            other,
            extra={"run_id": run_id},
        )
    return len(stale)


async def serve(
    app: Brevia, settings: BreviaSettings, stop: asyncio.Event | None = None
) -> None:
    """Run the jobs of ``app`` until ``stop`` is set, or SIGINT or SIGTERM.

    On stop, running jobs are given ``worker_shutdown_seconds`` to end; those still
    running start again when the worker starts again with the same version.
    """
    stop = stop or asyncio.Event()
    backend = _runtime(app).backend
    if not isinstance(backend, DbosBackend):
        raise RuntimeError("The worker needs the job backend of the settings")
    release = engine_version(settings)
    await app.start()
    try:
        try:
            # Inside: a failure after DBOS has launched still destroys it.
            launch(app, backend, release, settings.worker_id)
            await DBOS.register_queue_async(
                QUEUE, worker_concurrency=settings.worker_concurrency
            )
            # Replaced at each start, so that every worker keeps it as it is here.
            await DBOS.apply_schedules_async(
                [
                    {
                        "schedule_name": CLEANUP,
                        "workflow_fn": workflow.run_cleanup,
                        "schedule": CLEANUP_SCHEDULE,
                    }
                ]
            )
            failed = await fail_other_versions(app, backend, release)
            logger.info(
                "Job worker %s started: version %s, %d jobs of other versions failed",
                settings.worker_id,
                release,
                failed,
            )
            _on_signals(stop)
            await stop.wait()
        finally:
            # DBOS waits here for running jobs, which run on this event loop.
            await asyncio.to_thread(
                DBOS.destroy,
                workflow_completion_timeout_sec=settings.worker_shutdown_seconds,
            )
            await _stop_running_jobs()
            workflow.install(None)
    finally:
        await app.stop()
    logger.info("Job worker %s stopped", settings.worker_id)


async def _stop_running_jobs() -> None:
    """Cancel the jobs still running on this event loop after the shutdown wait.

    A cancelled task records nothing: the job stays started in the engine and
    starts again when the worker starts again with the same identifier and version.
    """
    current = asyncio.current_task()
    running = [task for task in asyncio.all_tasks() if task is not current]
    for task in running:
        task.cancel()
    if running:
        await asyncio.gather(*running, return_exceptions=True)
        logger.warning("Job worker stopped %d running tasks", len(running))


def _on_signals(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for number in (signal.SIGINT, signal.SIGTERM):
        # Not available on every platform: the worker then stops with its process.
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(number, stop.set)
