"""The durable execution engine of jobs, seen from Brevia: queue, cancel, status.

:class:`DbosBackend` uses a DBOS client, which only reads and writes the DBOS tables
and never runs or migrates anything: every process that submits or reads jobs uses
it. A worker additionally launches DBOS to run the queued jobs (see
:mod:`brevia.jobs.worker`).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from typing import Literal, Protocol

from dbos import DBOSClient, EnqueueOptions
from pydantic import SecretStr
from sqlalchemy import Connection

from brevia.config.settings import BreviaSettings
from brevia.errors import Unavailable, cause_types

logger = logging.getLogger(__name__)

APP_NAME = "brevia"
"""Name of the application in the DBOS tables."""

QUEUE = "brevia_jobs"
"""Queue of the jobs."""

WORKFLOW = "brevia.job"
"""Name of the workflow that runs a job."""

CLEANUP = "brevia.cleanup"
"""Name of the scheduled workflow that deletes expired data."""

ENDED = ["SUCCESS", "ERROR", "CANCELLED", "MAX_RECOVERY_ATTEMPTS_EXCEEDED"]
"""Engine statuses of a workflow that has ended."""

DELETE_BATCH = 500
"""Workflows deleted at a time."""

Settle = Callable[[list[tuple[str, str]]], Awaitable[None]]
"""Reconciles the records of ended jobs from their engine statuses."""

THREADS = 4
"""Threads for the blocking calls of the DBOS client."""

EngineStatus = Literal[
    "ENQUEUED",
    "DELAYED",
    "PENDING",
    "SUCCESS",
    "ERROR",
    "CANCELLED",
    "MAX_RECOVERY_ATTEMPTS_EXCEEDED",
]


ENGINE_LOGGER = "dbos"
"""Logger of the engine."""

ENGINE_CONSOLE_HANDLER = "__dbos_console_log_handler__"
"""Handler that the engine adds to its logger when it is launched."""


class _EngineRecords(logging.Filter):
    """Keeps the records of the engine free of data and of database details.

    Messages stop before their first ``": "``, after which the engine writes the text
    of an exception, a value or a database URL; exceptions are reduced to their type,
    since their messages and chains may hold driver messages (host, user, database)
    or data of a job. Debug records are dropped.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.INFO:
            return False
        try:
            message = record.getMessage()
        except Exception:  # a filter must not raise into the code that logs
            message = "Record of the engine that cannot be formatted"
        message = message.split(": ", 1)[0]
        if record.exc_info and record.exc_info[1] is not None:
            message = f"{message} ({type(record.exc_info[1]).__name__})"
        record.msg = message
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def guard_engine_logs() -> None:
    """Filter the records of the engine and send them to the handlers of the
    application, instead of the console handler of the engine. Repeatable."""
    engine = logging.getLogger(ENGINE_LOGGER)
    if not any(isinstance(item, _EngineRecords) for item in engine.filters):
        engine.addFilter(_EngineRecords())
    for handler in list(engine.handlers):
        if handler.name == ENGINE_CONSOLE_HANDLER:
            engine.removeHandler(handler)
    engine.propagate = True


class JobBackend(Protocol):
    """Operations of Brevia on the durable state of jobs."""

    async def start(self) -> None:
        """Connect to the durable state and check that it can be used.

        Raises:
            Unavailable: It cannot be reached or is not migrated.
        """

    async def stop(self) -> None:
        """Release the connections. Calling it again does nothing."""

    def enqueue(self, connection: Connection | None, run_id: str) -> None:
        """Queue the job ``run_id``, in the transaction of ``connection`` if given."""

    async def cancel(self, run_id: str) -> None:
        """Cancel the job ``run_id``; nothing happens if it has ended."""

    async def status(self, run_id: str) -> EngineStatus | None:
        """Status of the job in the engine, or ``None`` when it is unknown."""

    async def statuses(self, run_ids: list[str]) -> dict[str, EngineStatus]:
        """Statuses in the engine of the jobs ``run_ids`` it knows, in one read."""

    async def delete_ended(
        self, before: datetime, *, dry_run: bool, settle: Settle | None = None
    ) -> int:
        """Delete the recorded steps of jobs ended before ``before``, after giving
        their engine statuses to ``settle``."""


class DbosBackend:
    """Job backend on DBOS, in the jobs schema of the Brevia database."""

    def __init__(self, url: str, schema: str) -> None:
        self.url = SecretStr(url)
        self.schema = schema
        self._client: DBOSClient | None = None
        # Its own threads: a launched DBOS replaces the default executor of the event
        # loop and shuts it down when destroyed.
        self._executor: ThreadPoolExecutor | None = None

    @classmethod
    def from_settings(cls, settings: BreviaSettings) -> DbosBackend:
        return cls(settings.database_url.get_secret_value(), settings.jobs_schema)

    @property
    def client(self) -> DBOSClient:
        if self._client is None:
            raise RuntimeError("The job backend is not started")
        return self._client

    async def start(self) -> None:
        if self._client is not None:
            raise RuntimeError("The job backend is already started")
        guard_engine_logs()
        self._executor = ThreadPoolExecutor(THREADS, thread_name_prefix="brevia-jobs")
        failure: Unavailable | None = None
        try:
            client = await self._call(
                partial(
                    DBOSClient,
                    system_database_url=self.url.get_secret_value(),
                    dbos_system_schema=self.schema,
                    application_name=APP_NAME,
                    retry_connection_errors=False,
                )
            )
        except Exception as exc:
            failure = Unavailable(
                "Job state cannot be reached",
                {"schema": self.schema, "cause": cause_types(exc)},
            )
        if failure is not None:
            # Raised outside the except block: driver messages may hold the host.
            self._shutdown()
            raise failure
        try:
            await self._call(partial(client.list_workflows, limit=1, load_input=False))
        except Exception as exc:
            failure = Unavailable(
                "Job schema is not migrated: run `brevia db upgrade`",
                {"schema": self.schema, "cause": cause_types(exc)},
            )
        if failure is not None:
            await self._call(client.destroy)
            self._shutdown()
            raise failure
        self._client = client
        logger.info("Job backend started: schema %s", self.schema)

    async def stop(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await self._call(client.destroy)
        self._shutdown()

    def _shutdown(self) -> None:
        executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=False)

    async def _call[T](self, function: Callable[[], T]) -> T:
        """Run a blocking function of the client in the threads of the backend."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, function)

    def enqueue(self, connection: Connection | None, run_id: str) -> None:
        # No application version: a queued job runs on any worker, also of a newer
        # release; an interrupted one starts again only on its own (specification
        # §11.5).
        options: EnqueueOptions = {
            "workflow_name": WORKFLOW,
            "queue_name": QUEUE,
            "workflow_id": run_id,
            "application_name": APP_NAME,
        }
        if connection is None:
            self.client.enqueue(options, run_id)
        else:
            self.client.enqueue_in_transaction(connection, options, run_id)

    async def cancel(self, run_id: str) -> None:
        await self._engine("cancel", partial(self.client.cancel_workflow, run_id))

    async def status(self, run_id: str) -> EngineStatus | None:
        found = await self._engine(
            "status",
            partial(
                self.client.list_workflows,
                workflow_ids=[run_id],
                load_input=False,
                load_output=False,
            ),
        )
        return found[0].status if found else None

    async def statuses(self, run_ids: list[str]) -> dict[str, EngineStatus]:
        found = await self._engine(
            "statuses",
            partial(
                self.client.list_workflows,
                workflow_ids=run_ids,
                load_input=False,
                load_output=False,
            ),
        )
        return {status.workflow_id: status.status for status in found}

    async def pending(self) -> list[tuple[str, str | None]]:
        """Identifiers and versions of the jobs started and not ended."""
        found = await self._engine(
            "pending",
            partial(
                self.client.list_workflows,
                status="PENDING",
                name=WORKFLOW,
                load_input=False,
                load_output=False,
            ),
        )
        return [(status.workflow_id, status.app_version) for status in found]

    async def delete_ended(
        self, before: datetime, *, dry_run: bool, settle: Settle | None = None
    ) -> int:
        """Delete the recorded steps of jobs and cleanups ended before ``before``;
        with ``dry_run``, only count them. Jobs that have not ended are never
        deleted: they may start again.

        ``settle`` receives the identifiers and engine statuses of the jobs of each
        batch before it is deleted, so that their records can be reconciled: once
        deleted, the engine no longer knows how they ended."""
        total = 0
        while True:
            found = await self._engine(
                "list_ended",
                partial(
                    self.client.list_workflows,
                    name=[WORKFLOW, CLEANUP],
                    status=ENDED,
                    completed_before=before.isoformat(),
                    limit=DELETE_BATCH,
                    offset=total if dry_run else None,
                    load_input=False,
                    load_output=False,
                ),
            )
            if not dry_run and found:
                if settle is not None:
                    await settle(
                        [(s.workflow_id, s.status) for s in found if s.name == WORKFLOW]
                    )
                ids = [status.workflow_id for status in found]
                await self._engine(
                    "delete_ended", partial(self.client.delete_workflows, ids)
                )
            total += len(found)
            if len(found) < DELETE_BATCH:
                return total

    async def _engine[T](self, operation: str, function: Callable[[], T]) -> T:
        """Run ``function``; errors of the engine become ``Unavailable``."""
        failure: Unavailable | None = None
        try:
            return await self._call(function)
        except Exception as exc:
            failure = Unavailable(
                "Job state operation failed",
                {"operation": operation, "cause": cause_types(exc)},
            )
        raise failure
