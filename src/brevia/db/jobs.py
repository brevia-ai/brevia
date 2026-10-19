"""Records of jobs: their rows in ``runs``.

The functions run inside a transaction of :class:`~brevia.db.store.SqlStore`. A job
step may run more than once (a worker can stop after the step did its work and before
its result was checkpointed), so every write is idempotent. The outcome and the model
calls of a job that ran its activity are written as those of a direct run
(:meth:`~brevia.db.store.SqlStore.finish_run`).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Connection, RowMapping, and_, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

from brevia.db.tables import model_calls, runs
from brevia.errors import Unavailable, cause_types

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
ACTIVE: tuple[JobStatus, ...] = ("queued", "running")
"""Statuses of a job that has not ended."""

Enqueue = Callable[[Connection | None], None]
"""Queues a recorded job, in the transaction of its record when given a connection."""


@dataclass(frozen=True)
class NewJob:
    """A job at its submission."""

    id: uuid.UUID
    activity: str
    activity_version: str
    input: Mapping[str, Any]
    overrides: Mapping[str, Any]
    idempotency_key: str | None
    fingerprint: str
    retry_of_run_id: uuid.UUID | None
    created_at: datetime
    caller: str | None = None  # None for trusted code in the process
    end_user: str | None = None


@dataclass(frozen=True)
class JobRecord:
    """A job as recorded; ``snapshot`` is ``None`` until it starts."""

    id: uuid.UUID
    activity: str
    activity_version: str
    status: JobStatus
    input: Mapping[str, Any]
    overrides: Mapping[str, Any]
    snapshot: Mapping[str, Any] | None
    result: Mapping[str, Any] | None
    error: Mapping[str, Any] | None
    usage: Mapping[str, Any] | None
    idempotency_key: str | None
    fingerprint: str
    retry_of_run_id: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    deadline_at: datetime | None
    finished_at: datetime | None
    caller: str | None = None
    end_user: str | None = None


@dataclass(frozen=True)
class JobQuery:
    """Which jobs to list, newest first: ``after`` is the position of the last job of
    the previous page, ``(created_at, id)``."""

    limit: int
    owner: str | None = None  # None for the jobs of every caller
    activity: str | None = None
    statuses: tuple[JobStatus, ...] = ()  # empty for every status
    idempotency_key: str | None = None
    after: tuple[datetime, uuid.UUID] | None = None


def record(row: RowMapping) -> JobRecord:
    return JobRecord(
        id=row["id"],
        activity=row["activity"],
        activity_version=row["activity_version"],
        status=row["status"],
        input=row["input"],
        overrides=row["overrides"] or {},
        snapshot=row["snapshot"],
        result=row["result"],
        error=row["error"],
        usage=row["usage"],
        idempotency_key=row["idempotency_key"],
        fingerprint=row["fingerprint"],
        retry_of_run_id=row["retry_of_run_id"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        deadline_at=row["deadline_at"],
        finished_at=row["finished_at"],
        caller=row["caller"],
        end_user=row["end_user"],
    )


async def read(connection: AsyncConnection, run_id: uuid.UUID) -> JobRecord | None:
    """The job ``run_id``, or ``None`` when there is no such job."""
    row = (
        (
            await connection.execute(
                select(runs).where(runs.c.id == run_id, runs.c.mode == "job")
            )
        )
        .mappings()
        .first()
    )
    return None if row is None else record(row)


async def find(
    connection: AsyncConnection,
    caller: str | None,
    activity: str,
    idempotency_key: str,
) -> JobRecord | None:
    """The job of ``caller`` and ``activity`` recorded with ``idempotency_key``."""
    row = (
        (
            await connection.execute(
                select(runs).where(
                    runs.c.caller.is_not_distinct_from(caller),
                    runs.c.activity == activity,
                    runs.c.idempotency_key == idempotency_key,
                )
            )
        )
        .mappings()
        .first()
    )
    return None if row is None else record(row)


async def page(connection: AsyncConnection, query: JobQuery) -> list[JobRecord]:
    """The jobs that match ``query``, newest first, at most ``query.limit``."""
    statement = select(runs).where(runs.c.mode == "job")
    if query.owner is not None:
        statement = statement.where(runs.c.caller == query.owner)
    if query.activity is not None:
        statement = statement.where(runs.c.activity == query.activity)
    if query.statuses:
        statement = statement.where(runs.c.status.in_(query.statuses))
    if query.idempotency_key is not None:
        statement = statement.where(runs.c.idempotency_key == query.idempotency_key)
    if query.after is not None:
        statement = statement.where(
            tuple_(runs.c.created_at, runs.c.id) < tuple_(*query.after)
        )
    statement = statement.order_by(runs.c.created_at.desc(), runs.c.id.desc()).limit(
        query.limit
    )
    rows = (await connection.execute(statement)).mappings().all()
    return [record(row) for row in rows]


async def submit(
    connection: AsyncConnection, job: NewJob, enqueue: Enqueue
) -> tuple[JobRecord, bool]:
    """Record and queue a job, or return the job recorded with the same key.

    Returns the record and whether it was created now. With an idempotency key, a
    concurrent submission with the same key waits for this one and then finds it.
    """
    statement = pg_insert(runs).values(
        id=job.id,
        caller=job.caller,
        end_user=job.end_user,
        activity=job.activity,
        activity_version=job.activity_version,
        mode="job",
        status="queued",
        input=job.input,
        overrides=job.overrides,
        idempotency_key=job.idempotency_key,
        fingerprint=job.fingerprint,
        retry_of_run_id=job.retry_of_run_id,
        created_at=job.created_at,
    )
    if job.idempotency_key is not None:
        statement = statement.on_conflict_do_nothing(
            index_elements=["caller", "activity", "idempotency_key"],
            index_where=runs.c.idempotency_key.is_not(None),
        )
    inserted = (
        (await connection.execute(statement.returning(*runs.c))).mappings().first()
    )
    if inserted is None:
        key = job.idempotency_key
        existing = (
            None
            if key is None
            else await find(connection, job.caller, job.activity, key)
        )
        if existing is None:
            raise Unavailable("The job of the idempotency key cannot be read")
        return existing, False
    failure: Unavailable | None = None
    try:
        await connection.run_sync(enqueue)
    except SQLAlchemyError:
        raise  # reported by the store, as every database error
    except Exception as exc:
        failure = Unavailable("The job cannot be queued", {"cause": cause_types(exc)})
    if failure is not None:
        # Raised outside the except block: engine messages may name the database.
        raise failure
    return record(inserted), True


async def start(
    connection: AsyncConnection,
    run_id: uuid.UUID,
    snapshot: Mapping[str, Any],
    now: datetime,
    deadline: datetime | None,
) -> JobRecord | None:
    """Mark a job as running with the values it resolved.

    The first start and deadline are kept when the step runs again. Returns ``None``
    when the job has already ended, for example because it was cancelled.
    """
    row = (
        (
            await connection.execute(
                update(runs)
                .where(runs.c.id == run_id, runs.c.status.in_(ACTIVE))
                .values(
                    status="running",
                    snapshot=snapshot,
                    started_at=func.coalesce(runs.c.started_at, now),
                    deadline_at=func.coalesce(runs.c.deadline_at, deadline),
                )
                .returning(*runs.c)
            )
        )
        .mappings()
        .first()
    )
    return None if row is None else record(row)


async def _usage(connection: AsyncConnection, run_id: uuid.UUID) -> dict[str, Any]:
    """Usage of a job as the sum of its recorded calls, as for a direct run."""
    unknown = func.count().filter(model_calls.c.cost_usd.is_(None))
    row = (
        await connection.execute(
            select(
                func.coalesce(func.sum(model_calls.c.requests), 0),
                func.coalesce(func.sum(model_calls.c.tool_calls), 0),
                func.coalesce(func.sum(model_calls.c.input_tokens), 0),
                func.coalesce(func.sum(model_calls.c.output_tokens), 0),
                func.coalesce(func.sum(model_calls.c.cache_read_tokens), 0),
                func.coalesce(func.sum(model_calls.c.cache_write_tokens), 0),
                func.coalesce(func.sum(model_calls.c.cost_usd), 0),
                unknown,
            ).where(model_calls.c.run_id == run_id)
        )
    ).one()
    cost: Decimal | None = None if row[7] else Decimal(row[6])
    return {
        "requests": row[0],
        "tool_calls": row[1],
        "input_tokens": row[2],
        "output_tokens": row[3],
        "cache_read_tokens": row[4],
        "cache_write_tokens": row[5],
        "cost_usd": None if cost is None else str(cost),
        "cost_kind": "unknown" if cost is None else "estimate",
    }


async def finish(
    connection: AsyncConnection,
    run_id: uuid.UUID,
    status: JobStatus,
    result: Mapping[str, Any] | None,
    error: Mapping[str, Any] | None,
    now: datetime,
) -> bool:
    """Record the end of a job unless it has already ended; returns whether it did.

    Used when the activity did not record the outcome itself: a cancellation, a
    failure before the start, a reconciliation from the engine. The usage is that of
    the calls recorded, if any.
    """
    usage = await _usage(connection, run_id)
    ended = (
        await connection.execute(
            update(runs)
            .where(and_(runs.c.id == run_id, runs.c.status.in_(ACTIVE)))
            .values(
                status=status,
                result=result,
                error=error,
                usage=usage,
                finished_at=now,
            )
            .returning(runs.c.id)
        )
    ).first()
    return ended is not None
