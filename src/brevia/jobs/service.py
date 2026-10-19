"""Operations on jobs behind :meth:`brevia.Brevia.submit` and :class:`RunHandle`.

The record in ``runs`` is the application view of a job; the engine holds its durable
state. The record is written by the job itself, by a cancellation and, when the job
ended without writing it (for example a failure to record its outcome), by
reconciliation with the engine when the job is read.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from brevia.access.access import Caller
from brevia.db.jobs import ACTIVE, JobQuery, JobRecord, JobStatus, NewJob
from brevia.db.values import recordable_json
from brevia.errors import (
    BreviaError,
    Busy,
    Cancelled,
    IdempotencyConflict,
    InternalError,
    InvalidInput,
    NotFound,
    NotReady,
    Unsupported,
    error_from_dict,
    validation_details,
)
from brevia.files.files import check_sources
from brevia.jobs.handle import JobPage, JobState, RunHandle
from brevia.jobs.runtime import JobRuntime
from brevia.runs.activities import Activity
from brevia.runs.execution import (
    check_key,
    from_record,
    recorded_input,
    resolved,
    validated_input,
)

logger = logging.getLogger(__name__)

POLL_SECONDS = 0.25
"""Interval between reads of a job while waiting for its result."""

MAX_PAGE = 100
"""Most jobs in a page of the list."""

RECONCILE_BATCH = 500
"""Active jobs whose engine status is read at once before a list."""

FAILED_ENDINGS = frozenset({"ERROR", "MAX_RECOVERY_ATTEMPTS_EXCEEDED", "SUCCESS"})
"""Engine statuses of a job that ended without recording its outcome."""


def fingerprint(
    activity: Activity, input: Mapping[str, Any], overrides: Mapping[str, Any]
) -> str:
    """SHA-256 of the canonical JSON of what a submission asks for."""
    data = {
        "activity": activity.name,
        "version": activity.version,
        "input": input,
        "overrides": overrides,
    }
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def engine_ending(status: str | None) -> tuple[JobStatus, dict[str, Any]] | None:
    """Status and error to record for a job the engine ended, from its engine
    status; ``None`` while the job is active for the engine too."""
    error: BreviaError
    if status == "CANCELLED":
        error = Cancelled("The job was cancelled")
        return "cancelled", error.to_dict()
    if status in FAILED_ENDINGS:
        error = InternalError(
            "The job ended without recording its outcome",
            {"engine_status": status},
            retryable=True,
        )
        return "failed", error.to_dict()
    return None


def job_state(record: JobRecord) -> JobState:
    return JobState(
        run_id=str(record.id),
        activity=record.activity,
        activity_version=record.activity_version,
        status=record.status,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        error=record.error,
        usage=record.usage,
        retry_of=None
        if record.retry_of_run_id is None
        else str(record.retry_of_run_id),
    )


def _cursor(record: JobRecord) -> str:
    """Opaque position of a job in the list."""
    text = f"{record.created_at.isoformat()} {record.id}"
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _position(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        text = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        created_at, run_id = text.split(" ")
        position = datetime.fromisoformat(created_at), uuid.UUID(run_id)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise InvalidInput("The cursor is not valid") from None
    if position[0].tzinfo is None:
        raise InvalidInput("The cursor is not valid")
    return position


def _run_id(run_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(run_id)
    except (ValueError, TypeError, AttributeError):
        raise NotFound("Job not found", {"run_id": str(run_id)}) from None


class JobService:
    """Jobs of one :class:`~brevia.Brevia` instance."""

    def __init__(self, runtime: JobRuntime) -> None:
        self._runtime = runtime
        self._backend = runtime.backend

    def handle(self, run_id: str, caller: Caller | None = None) -> RunHandle:
        return RunHandle(self, str(_run_id(run_id)), caller)

    async def submit(
        self,
        name: str,
        request: BaseModel | Mapping[str, Any],
        overrides: Mapping[str, Any] | None,
        idempotency_key: str | None,
        caller: Caller | None = None,
        retry_of: uuid.UUID | None = None,
    ) -> RunHandle:
        runtime = self._runtime
        activity = runtime.activity(name)
        if "job" not in activity.modes:
            raise Unsupported(
                f"Activity {name!r} does not support jobs", {"activity": name}
            )
        check_key(idempotency_key)
        payload = validated_input(activity, request)
        recorded = recorded_input(activity, payload)
        # The worker validates the recorded input: the schema must read it back.
        try:
            from_record(activity.input_type, recorded)
        except ValidationError as exc:
            raise InternalError(
                f"Input of activity {name!r} cannot be read back from its record: "
                "the input schema must accept its own JSON form",
                validation_details(exc),
            ) from None
        try:
            recorded_overrides = recordable_json(dict(overrides or {}))
        except ValueError as exc:
            raise InvalidInput(
                "Overrides of a job must have a finite JSON form",
                {"reason": str(exc)},
            ) from None
        digest = fingerprint(activity, recorded, recorded_overrides)
        if idempotency_key is not None:
            # A repeated submission gets the job accepted earlier, whatever the
            # configuration is now: it must not depend on later customisations.
            existing = await runtime.store.find_job(
                _name(caller), name, idempotency_key
            )
            if existing is not None:
                return self._found(existing, digest, caller)
        # Conditions of a new job, checked after the lookup by key, so that a
        # repeated submission finds its job also after a change of the settings.
        check_sources(runtime.files, payload, caller)
        # Checked now, as the worker will resolve them: a job that cannot start is
        # refused at once.
        await resolved(runtime.store, activity, recorded_overrides)
        job = NewJob(
            id=uuid.uuid4(),
            activity=name,
            activity_version=activity.version,
            input=recorded,
            overrides=recorded_overrides,
            idempotency_key=idempotency_key,
            fingerprint=digest,
            retry_of_run_id=retry_of,
            created_at=datetime.now(UTC),
            caller=_name(caller),
            end_user=None if caller is None else caller.end_user,
        )
        record, created = await runtime.store.submit_job(
            job, partial(self._backend.enqueue, run_id=str(job.id))
        )
        if not created:  # submitted meanwhile with the same key
            return self._found(record, digest, caller)
        logger.info(
            "Job submitted: %s",
            name,
            extra={"run_id": str(record.id), "activity": name},
        )
        return RunHandle(self, str(record.id), caller)

    def _found(
        self, record: JobRecord, digest: str, caller: Caller | None
    ) -> RunHandle:
        """The job recorded with the key of a submission with fingerprint ``digest``.

        Raises:
            IdempotencyConflict: The job was submitted with a different request.
        """
        if record.fingerprint != digest:
            raise IdempotencyConflict(
                "The idempotency key was used for a different request",
                {"run_id": str(record.id)},
            )
        logger.info(
            "Job found by its key: %s",
            record.activity,
            extra={"run_id": str(record.id), "activity": record.activity},
        )
        return RunHandle(self, str(record.id), caller)

    async def state(self, run_id: str, caller: Caller | None) -> JobState:
        return job_state(await self._record(run_id, caller))

    async def result(
        self, run_id: str, wait: float | None, caller: Caller | None
    ) -> BaseModel:
        give_up = time.monotonic() + (wait or 0)
        while True:
            record = await self._record(run_id, caller)
            if record.status == "succeeded":
                return self._output(record)
            if record.status in ("failed", "cancelled"):
                raise error_from_dict(dict(record.error or {}))
            left = give_up - time.monotonic()
            if left <= 0:
                raise NotReady(
                    "The job has not ended",
                    {"run_id": run_id, "status": record.status},
                )
            await asyncio.sleep(min(POLL_SECONDS, left))

    async def cancel(self, run_id: str, caller: Caller | None) -> JobState:
        record = await self._record(run_id, caller)
        if record.status in ACTIVE:
            # Recorded before the engine stops the run, so that the run finds the job
            # cancelled and adds its calls to it, instead of taking its stop for a
            # stop of the worker.
            error = Cancelled("The job was cancelled")
            await self._end(record, "cancelled", error.to_dict())
            record = await self._record(run_id, caller)
        if record.status == "cancelled":
            # Also repeated, so that calling it again completes a cancellation whose
            # engine part failed; it does nothing on a job ended in the engine.
            await self._backend.cancel(str(record.id))
        return job_state(record)

    async def retry(
        self, run_id: str, idempotency_key: str | None, caller: Caller | None
    ) -> RunHandle:
        record = await self._record(run_id, caller)
        if record.status in ACTIVE:
            raise Busy("The job has not ended", {"status": record.status})
        if record.status == "succeeded":
            raise Unsupported("Only a failed or cancelled job can be retried")
        # The new job belongs to the caller of the failed one.
        owner = (
            None if record.caller is None else Caller(record.caller, record.end_user)
        )
        retried = await self.submit(
            record.activity,
            record.input,
            record.overrides,
            idempotency_key,
            caller=owner,
            retry_of=record.id,
        )
        return RunHandle(self, retried.run_id, caller)

    async def file(self, run_id: str, name: str, caller: Caller | None) -> Path:
        record = await self._record(run_id, caller)
        files = self._runtime.files
        if files is None:
            raise NotFound("File not found", {"name": name})
        return files.output_path(str(record.id), name)

    async def page(
        self,
        caller: Caller | None,
        *,
        activity: str | None,
        status: JobStatus | None,
        idempotency_key: str | None,
        limit: int,
        cursor: str | None,
    ) -> JobPage:
        self._runtime.check_started()
        check_key(idempotency_key)
        if not 1 <= limit <= MAX_PAGE:
            raise InvalidInput(
                f"The limit must be between 1 and {MAX_PAGE}", {"limit": limit}
            )
        query = JobQuery(
            limit=limit + 1,  # one more, to know whether there is a next page
            owner=self._runtime.access.visible_caller(caller),
            activity=activity,
            statuses=() if status is None else (status,),
            idempotency_key=idempotency_key,
            after=None if cursor is None else _position(cursor),
        )
        # Before the list, so that its filter, order and pages see the statuses
        # the jobs would have when read one by one.
        await self._reconcile_active(query)
        records = await self._runtime.store.list_jobs(query)
        more = len(records) > limit
        records = records[:limit]
        next_cursor = _cursor(records[-1]) if more else None
        return JobPage(jobs=[job_state(r) for r in records], next_cursor=next_cursor)

    async def _reconcile_active(self, query: JobQuery) -> None:
        """End the active jobs the list may show that the engine has ended."""
        active = replace(query, limit=RECONCILE_BATCH, statuses=ACTIVE, after=None)
        while records := await self._runtime.store.list_jobs(active):
            engine = await self._backend.statuses([str(r.id) for r in records])
            for record in records:
                ending = engine_ending(engine.get(str(record.id)))
                if ending is not None:
                    await self._end(record, *ending)
            if len(records) < RECONCILE_BATCH:
                return
            last = records[-1]
            active = replace(active, after=(last.created_at, last.id))

    async def find(
        self, activity: str, idempotency_key: str, caller: Caller | None
    ) -> JobState | None:
        self._runtime.check_started()
        check_key(idempotency_key)
        record = await self._runtime.store.find_job(
            _name(caller), activity, idempotency_key
        )
        return None if record is None else job_state(await self._reconciled(record))

    async def _record(self, run_id: str, caller: Caller | None) -> JobRecord:
        """The record of a job, reconciled with the engine while it is active.

        A job that ``caller`` may not see is not found, as one that does not exist:
        its existence is not revealed.
        """
        self._runtime.check_started()
        key = _run_id(run_id)
        record = await self._runtime.store.job(key)
        if record is None or not self._runtime.access.sees(caller, record.caller):
            raise NotFound("Job not found", {"run_id": str(run_id)})
        return await self._reconciled(record)

    async def _reconciled(self, record: JobRecord) -> JobRecord:
        """The record, ended as the engine says when the job ended without writing
        its outcome."""
        if record.status not in ACTIVE:
            return record
        ending = engine_ending(await self._backend.status(str(record.id)))
        if ending is None:
            return record
        await self._end(record, *ending)
        return await self._runtime.store.job(record.id) or record

    async def _end(
        self, record: JobRecord, status: JobStatus, error: Mapping[str, Any]
    ) -> None:
        if await self._runtime.store.finish_job(
            record.id, status, None, error, datetime.now(UTC)
        ):
            logger.warning(
                "Job %s: %s",
                status,
                record.activity,
                extra={"run_id": str(record.id), "activity": record.activity},
            )

    def _output(self, record: JobRecord) -> BaseModel:
        activity = self._runtime.activity(record.activity)
        try:
            return from_record(activity.output_type, record.result)
        except ValidationError:
            raise InternalError(
                "The recorded result does not match the output schema of the activity",
                {"activity_version": record.activity_version},
            ) from None


def _name(caller: Caller | None) -> str | None:
    return None if caller is None else caller.name
