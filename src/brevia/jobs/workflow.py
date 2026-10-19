"""The durable workflow that runs a job, and its steps.

One generic workflow runs every job by its identifier, in two steps checkpointed by
DBOS:

1. ``brevia.prepare`` reads the job, the customisations and the prompts, resolves the
   configuration and records the snapshot and the deadline. A job started again uses
   the values of this checkpoint, even if the customisations changed meanwhile.
2. ``brevia.run`` runs the activity and records its outcome and model calls, as a
   direct run does. The engine stops it when the job is cancelled. If the worker
   stops before the step ends, the step runs again from the start: the model calls of
   the lost execution are made, and paid, again, and are not recorded.

A job that fails before running its activity records its failure in a final step,
``brevia.finish``.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from dbos import DBOS
from dbos import error as dbos_error
from pydantic import BaseModel

from brevia.db.jobs import ACTIVE, JobStatus
from brevia.errors import BreviaError, InternalError, Unsupported
from brevia.files.retention import clean
from brevia.jobs.backend import CLEANUP, WORKFLOW
from brevia.jobs.runtime import JobRuntime
from brevia.runs.activities import Activity
from brevia.runs.context import RunContext
from brevia.runs.execution import (
    recorded_error,
    recorded_snapshot,
    resolved,
    run_timeout,
    snapshot,
    stack_frames,
    validated_input,
)

logger = logging.getLogger(__name__)

MAX_RESTARTS = 3
"""Starts of a job after the first, when its worker stopped while it ran; then the
engine ends it as failed. Each start runs the activity, and its model calls, again."""

_runtime: JobRuntime | None = None
"""The application whose activities the jobs of this process run."""

_version: str | None = None
"""Version of the application the engine runs the jobs under, in their snapshots."""


def install(runtime: JobRuntime | None, version: str | None = None) -> None:
    """Make the application of ``runtime`` run the jobs of this process, under
    ``version``; ``None`` removes it.

    DBOS is one instance per process, so one application runs the jobs of a worker.
    """
    global _runtime, _version
    _runtime, _version = runtime, version


def _installed() -> JobRuntime:
    if _runtime is None:
        raise RuntimeError("No Brevia application runs the jobs of this process")
    return _runtime


@dataclass(frozen=True)
class Prepared:
    """Values resolved by the first step, checkpointed for a start again."""

    payload: BaseModel
    config: BaseModel
    overrides: dict[str, Any]
    snapshot: dict[str, Any]
    deadline: datetime | None  # None without a limit of duration


async def _prepare(run_id: str) -> Prepared | None:
    """Resolve the job; ``None`` when it has already ended, for example cancelled.

    Raises:
        Unsupported: The activity is now at a different version.
        BreviaError: The input or the configuration is not valid.
    """
    runtime = _installed()
    key = uuid.UUID(run_id)
    record = await runtime.store.job(key)
    if record is None:
        raise InternalError("The record of the job is missing", {"run_id": run_id})
    if record.status not in ACTIVE:
        return None
    activity = runtime.activity(record.activity)
    _check_version(activity, record.activity_version)
    payload = validated_input(activity, record.input)
    config, prompts = await resolved(runtime.store, activity, record.overrides)
    values = snapshot(
        runtime.project, _version, activity, config, record.overrides, prompts
    )
    now = datetime.now(UTC)
    started = await runtime.store.start_job(
        key,
        recorded_snapshot(activity, values),
        now,
        now + timedelta(seconds=activity.limits.max_seconds)
        if activity.limits.max_seconds
        else None,
    )
    if started is None:
        return None
    return Prepared(
        payload, config, dict(record.overrides), values, started.deadline_at
    )


def _check_version(activity: Activity, submitted: str) -> None:
    """Refuse to run a job with another version of its activity.

    Raises:
        Unsupported: The activity is now at another version; retryable.
    """
    if activity.version != submitted:
        raise Unsupported(
            f"Activity {activity.name!r} is now at version {activity.version}, the "
            f"job was submitted for version {submitted}: retry it",
            {"version": activity.version, "submitted": submitted},
            retryable=True,
        )


async def _step[T](
    name: str, work: Callable[[], Awaitable[T]], *, preemptible: bool = False
) -> T:
    """Run ``work`` as the durable step ``name``.

    The step is given to DBOS without arguments: DBOS logs the function of a step
    whose task is cancelled, and the arguments must not appear in logs. A
    ``preemptible`` step is stopped when the job is cancelled.
    """

    async def step() -> T:
        return await work()

    return await DBOS.run_step_async({"name": name, "preemptible": preemptible}, step)


async def _finish(
    run_id: str,
    status: JobStatus,
    result: Any,
    error: Any,
) -> None:
    await _installed().store.finish_job(
        uuid.UUID(run_id), status, result, error, datetime.now(UTC)
    )


async def _record_failure(run_id: str, error: BreviaError) -> None:
    """Record a failure before the activity ran, in the final step.

    A failure raised when the job is started again, after its run step was recorded,
    finds the position of the final step taken: the outcome is then written
    directly. The write changes only a job that has not ended, so repeating it is
    harmless.
    """
    recorded = recorded_error(error.to_dict())
    try:
        await _step("brevia.finish", lambda: _finish(run_id, "failed", None, recorded))
    except dbos_error.DBOSUnexpectedStepError:
        await _finish(run_id, "failed", None, recorded)


@DBOS.workflow(name=CLEANUP)
async def run_cleanup(scheduled_at: datetime, context: Any) -> None:
    """Daily cleanup of expired data, scheduled by the workers (see
    :mod:`brevia.files.retention`). The engine runs it once per schedule, whatever the
    number of workers."""
    runtime = _installed()
    await _step(
        CLEANUP,
        lambda: clean(
            runtime.store,
            runtime.backend,
            runtime.project.traces.retention_days,
            files=runtime.files,
        ),
    )


@DBOS.workflow(name=WORKFLOW, max_recovery_attempts=MAX_RESTARTS)
async def run_job(run_id: str) -> None:
    """Run the job ``run_id`` and record its outcome.

    A failure is recorded and raised, so that the engine records it too. A
    cancellation of the job ends the workflow: the cancellation records it.
    """
    runtime = _installed()
    extra: dict[str, Any] = {"run_id": run_id}
    try:
        prepared = await _step("brevia.prepare", lambda: _prepare(run_id))
        if prepared is None:
            logger.info("Job already ended, not run", extra=extra)
            return
        activity = runtime.activity(prepared.snapshot["activity"]["name"])
        # Checked again: a job started again takes its first step from the
        # checkpoint, without the check of _prepare, and the worker may now run
        # another version of the activity under the same engine version.
        _check_version(activity, prepared.snapshot["activity"]["version"])
    except BreviaError as exc:
        logger.warning("Job failed: %s", exc.code, extra=extra)
        await _record_failure(run_id, exc)
        raise
    except Exception as exc:
        logger.error(
            "Job failed unexpectedly with %s\n%s",
            type(exc).__name__,
            stack_frames(exc),
            extra=extra,
        )
        error = InternalError(f"The job failed unexpectedly: {type(exc).__name__}")
        await _record_failure(run_id, error)
        raise error from None
    # Failures inside are recorded by the run itself, as for a direct run.
    await _step(
        "brevia.run",
        lambda: _run(runtime, activity, run_id, prepared),
        preemptible=True,
    )


async def _run(
    runtime: JobRuntime, activity: Activity, run_id: str, prepared: Prepared
) -> None:
    """Run the activity with the prepared values and record its outcome.

    Nothing runs for a job that has already ended: its outcome may have been written
    by an execution that stopped before the engine recorded the end of this step.
    """
    record = await runtime.store.job(uuid.UUID(run_id))
    if record is None or record.status not in ACTIVE:
        return
    left = (
        None
        if prepared.deadline is None
        else (prepared.deadline - datetime.now(UTC)).total_seconds()
    )
    ctx: RunContext[Any] = RunContext(
        run_id=run_id,
        config=prepared.config,
        snapshot=prepared.snapshot,
        seconds_left=left,
        files=runtime.files,
    )
    if left is not None and left <= 0:
        # Started again after its deadline, for example after a stop of the worker.
        error = run_timeout(activity.limits.max_seconds)
        await runtime.executor.record(ctx, "failed", error=error.to_dict())
        raise error
    await runtime.executor.run(
        activity, prepared.payload, ctx, prepared.overrides, record=True, read_back=True
    )
