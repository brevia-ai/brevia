"""Store of the records Brevia keeps in the database.

:class:`Store` lists the operations the application needs; :class:`SqlStore` implements
them on PostgreSQL. The store holds no domain logic: the application decides what to
record and the store writes it.

Each operation uses its own short transaction and returns its connection to the pool:
no connection is held while an activity runs or a model answers. Database errors
become :class:`~brevia.errors.Unavailable` with the types of their causes only, since
driver messages may contain host names, users or data; the original exception is
neither the cause nor the context of the error, so tracebacks do not show it either.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from brevia.config.settings import BreviaSettings
from brevia.db import cleanup, customizations, feedback, jobs, migrate, runs
from brevia.db.customizations import (
    ConfigurationChange,
    Customizations,
    PromptOperation,
    StoredConfiguration,
    StoredPrompt,
    StoredRevision,
)
from brevia.db.engine import async_engine
from brevia.db.feedback import FeedbackRecord, RunOwner
from brevia.db.jobs import Enqueue, JobQuery, JobRecord, JobStatus, NewJob
from brevia.db.runs import NewRun, RunOutcome
from brevia.errors import Unavailable, cause_types

logger = logging.getLogger(__name__)


class Store(Protocol):
    """Operations on the records of Brevia."""

    async def start(self) -> None:
        """Open the store and check that it can be used.

        Raises:
            Unavailable: The database cannot be reached or is not migrated.
        """

    async def stop(self) -> None:
        """Release the resources of the store. Calling it again does nothing."""

    async def check(self) -> None:
        """Check, now, that the started store answers and its schema is migrated.

        Raises:
            Unavailable: The database cannot be reached or is not migrated.
        """

    async def create_run(self, run: NewRun) -> None:
        """Record a run that starts.

        Raises:
            Unavailable: The run cannot be recorded.
        """

    async def finish_run(self, outcome: RunOutcome) -> None:
        """Record the end of a run, its model calls and their contents, if any, in
        one transaction.

        Only a run that has not ended is changed. A job ends as cancelled only
        through its cancellation: a job cancelled meanwhile keeps its status and
        receives the usage and the calls of the run, and the cancelled outcome of a
        job still running, which a stop of its worker produces, is not written (the
        job starts again). An outcome already written, by an earlier execution of a
        job that stopped before its engine recorded the end, is not written again.

        Raises:
            Unavailable: The outcome cannot be recorded.
        """

    async def run_owner(self, run_id: uuid.UUID) -> RunOwner | None:
        """The owner of the run ``run_id``, direct or job; ``None`` when there is no
        such run.

        Raises:
            Unavailable: It cannot be read.
        """

    async def add_feedback(self, record: FeedbackRecord) -> tuple[FeedbackRecord, bool]:
        """Record feedback on a run that exists, or return the feedback that the same
        caller recorded on the same run with the same idempotency key.

        Returns the record and whether it was created now.

        Raises:
            Unavailable: It cannot be recorded.
        """

    async def customizations(self, activity: str) -> Customizations:
        """Customisations of the configuration and of the prompts of an activity.

        Raises:
            Unavailable: They cannot be read.
        """

    async def save_configuration(
        self,
        activity: str,
        change: ConfigurationChange,
        *,
        expected_version: int | None,
        author: str | None,
        now: datetime,
    ) -> StoredConfiguration:
        """Replace the customisation with ``change(current)`` and increment its
        version, atomically: concurrent changes are applied one after the other.

        Raises:
            VersionConflict: ``expected_version`` is given and is not current.
            Unavailable: The database cannot be used.
        """

    async def save_prompt(
        self,
        activity: str,
        name: str,
        text: str | None,
        *,
        operation: PromptOperation,
        sha256: str | None,
        expected_version: int | None,
        author: str | None,
        now: datetime,
    ) -> StoredPrompt:
        """Set the customised text of a prompt (``None`` for the file), increment
        its version and add a revision, in one transaction.

        Raises:
            VersionConflict: ``expected_version`` is given and is not current.
            Unavailable: The database cannot be used.
        """

    async def prompt_history(self, activity: str, name: str) -> list[StoredRevision]:
        """Revisions of a prompt, the most recent first.

        Raises:
            Unavailable: They cannot be read.
        """

    async def clear_expired_contents(self, now: datetime, *, dry_run: bool) -> int:
        """Clear the contents of model calls expired at ``now``; with ``dry_run``,
        only count them. Returns their number.

        Raises:
            Unavailable: The database cannot be used.
        """

    async def submit_job(self, job: NewJob, enqueue: Enqueue) -> tuple[JobRecord, bool]:
        """Record a job and queue it with ``enqueue`` in the same transaction, or
        return the job recorded with the same idempotency key.

        Returns the record and whether it was created now.

        Raises:
            Unavailable: The job cannot be recorded or queued.
        """

    async def job(self, run_id: uuid.UUID) -> JobRecord | None:
        """The job ``run_id``, or ``None`` when there is no such job.

        Raises:
            Unavailable: It cannot be read.
        """

    async def find_job(
        self, caller: str | None, activity: str, idempotency_key: str
    ) -> JobRecord | None:
        """The job of ``caller`` and ``activity`` submitted with ``idempotency_key``.

        A key is scoped to its caller: the same key of another caller is another job;
        ``None`` is the caller of trusted code in the process.

        Raises:
            Unavailable: It cannot be read.
        """

    async def list_jobs(self, query: JobQuery) -> list[JobRecord]:
        """The jobs that match ``query``, newest first, as recorded.

        Raises:
            Unavailable: They cannot be read.
        """

    async def start_job(
        self,
        run_id: uuid.UUID,
        snapshot: Mapping[str, Any],
        now: datetime,
        deadline: datetime | None,
    ) -> JobRecord | None:
        """Mark a job as running, keeping its first start and deadline; ``None``
        when it has already ended.

        Raises:
            Unavailable: It cannot be recorded.
        """

    async def finish_job(
        self,
        run_id: uuid.UUID,
        status: JobStatus,
        result: Mapping[str, Any] | None,
        error: Mapping[str, Any] | None,
        now: datetime,
    ) -> bool:
        """Record the end of a job that did not run its activity, for example a
        cancellation or a failure before the start, unless it has already ended;
        returns whether it was recorded.

        Raises:
            Unavailable: It cannot be recorded.
        """


def _unavailable(operation: str, exc: BaseException) -> Unavailable:
    return Unavailable(
        "Database operation failed",
        {"operation": operation, "cause": cause_types(exc)},
    )


class SqlStore:
    """Store on PostgreSQL, in the schema of the settings.

    The engine and its pool are created by :meth:`start` and closed by :meth:`stop`.
    """

    def __init__(self, settings: BreviaSettings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Engine of the started store.

        Raises:
            RuntimeError: The store is not started.
        """
        if self._engine is None:
            raise RuntimeError("The store is not started")
        return self._engine

    async def start(self) -> None:
        if self._engine is not None:
            raise RuntimeError("The store is already started")
        engine = async_engine(self._settings)
        try:
            revision = await self._revision(engine, "start")
        except BaseException:
            await engine.dispose()
            raise
        self._engine = engine
        schema = self._settings.database_schema
        logger.info("Database store started: schema %s, revision %s", schema, revision)

    async def check(self) -> None:
        await self._revision(self.engine, "check")

    async def _revision(self, engine: AsyncEngine, operation: str) -> str | None:
        """The migrated revision of the schema, checked against the expected one."""
        schema = self._settings.database_schema
        expected = migrate.head()
        failure: Unavailable | None = None
        try:
            async with engine.connect() as connection:
                revision: str | None = await connection.run_sync(
                    migrate.current, schema
                )
        except SQLAlchemyError as exc:
            failure = _unavailable(operation, exc)
        if failure is not None:
            # Raised outside the except block, so that the driver error is not even
            # the context of the exception.
            raise failure
        if revision != expected:
            raise Unavailable(
                "Database schema is not at the expected revision: run "
                "`brevia db upgrade`",
                {"schema": schema, "revision": revision, "expected": expected},
            )
        return revision

    async def stop(self) -> None:
        engine, self._engine = self._engine, None
        if engine is not None:
            await engine.dispose()

    async def create_run(self, run: NewRun) -> None:
        await self._transaction(
            "create_run", lambda connection: runs.create(connection, run)
        )

    async def clear_expired_contents(self, now: datetime, *, dry_run: bool) -> int:
        if dry_run:
            return await self._transaction(
                "count_expired",
                lambda connection: cleanup.count_expired(connection, now),
            )
        total = 0
        while True:  # short transactions, one batch each
            cleared = await self._transaction(
                "clear_expired",
                lambda connection: cleanup.clear_expired(connection, now),
            )
            total += cleared
            if cleared < cleanup.BATCH:
                return total

    async def submit_job(self, job: NewJob, enqueue: Enqueue) -> tuple[JobRecord, bool]:
        return await self._transaction(
            "submit_job", lambda connection: jobs.submit(connection, job, enqueue)
        )

    async def job(self, run_id: uuid.UUID) -> JobRecord | None:
        return await self._transaction(
            "job", lambda connection: jobs.read(connection, run_id)
        )

    async def list_jobs(self, query: JobQuery) -> list[JobRecord]:
        return await self._transaction(
            "list_jobs", lambda connection: jobs.page(connection, query)
        )

    async def start_job(
        self,
        run_id: uuid.UUID,
        snapshot: Mapping[str, Any],
        now: datetime,
        deadline: datetime | None,
    ) -> JobRecord | None:
        return await self._transaction(
            "start_job",
            lambda connection: jobs.start(connection, run_id, snapshot, now, deadline),
        )

    async def find_job(
        self, caller: str | None, activity: str, idempotency_key: str
    ) -> JobRecord | None:
        return await self._transaction(
            "find_job",
            lambda connection: jobs.find(connection, caller, activity, idempotency_key),
        )

    async def finish_job(
        self,
        run_id: uuid.UUID,
        status: JobStatus,
        result: Mapping[str, Any] | None,
        error: Mapping[str, Any] | None,
        now: datetime,
    ) -> bool:
        return await self._transaction(
            "finish_job",
            lambda connection: jobs.finish(
                connection, run_id, status, result, error, now
            ),
        )

    async def finish_run(self, outcome: RunOutcome) -> None:
        await self._transaction(
            "finish_run", lambda connection: runs.finish(connection, outcome)
        )

    async def run_owner(self, run_id: uuid.UUID) -> RunOwner | None:
        return await self._transaction(
            "run_owner", lambda connection: feedback.owner(connection, run_id)
        )

    async def add_feedback(self, record: FeedbackRecord) -> tuple[FeedbackRecord, bool]:
        return await self._transaction(
            "add_feedback", lambda connection: feedback.add(connection, record)
        )

    async def customizations(self, activity: str) -> Customizations:
        # One snapshot for both reads: a run never pairs a configuration with prompts
        # from a different moment.
        return await self._transaction(
            "customizations",
            lambda connection: customizations.read(connection, activity),
            isolation="REPEATABLE READ",
        )

    async def save_configuration(
        self,
        activity: str,
        change: ConfigurationChange,
        *,
        expected_version: int | None,
        author: str | None,
        now: datetime,
    ) -> StoredConfiguration:
        return await self._transaction(
            "save_configuration",
            lambda connection: customizations.save_configuration(
                connection,
                activity,
                change,
                expected_version=expected_version,
                author=author,
                now=now,
            ),
        )

    async def save_prompt(
        self,
        activity: str,
        name: str,
        text: str | None,
        *,
        operation: PromptOperation,
        sha256: str | None,
        expected_version: int | None,
        author: str | None,
        now: datetime,
    ) -> StoredPrompt:
        return await self._transaction(
            "save_prompt",
            lambda connection: customizations.save_prompt(
                connection,
                activity,
                name,
                text,
                operation=operation,
                sha256=sha256,
                expected_version=expected_version,
                author=author,
                now=now,
            ),
        )

    async def prompt_history(self, activity: str, name: str) -> list[StoredRevision]:
        return await self._transaction(
            "prompt_history",
            lambda connection: customizations.prompt_history(
                connection, activity, name
            ),
        )

    async def _transaction[T](
        self,
        operation: str,
        work: Callable[[AsyncConnection], Awaitable[T]],
        isolation: str | None = None,
    ) -> T:
        """Run ``work`` in one transaction, committed if it returns.

        Errors of Brevia raised by ``work`` (for example ``VersionConflict``) roll
        the transaction back and propagate unchanged.
        """
        if self._engine is None:
            raise Unavailable("Database store is not started", {"operation": operation})
        failure: Unavailable | None = None
        try:
            async with self._engine.connect() as connection:
                if isolation is not None:
                    await connection.execution_options(isolation_level=isolation)
                async with connection.begin():
                    return await work(connection)
        except SQLAlchemyError as exc:
            failure = _unavailable(operation, exc)
        # Raised outside the except block: no driver error as context.
        raise failure
