"""Records of feedback on runs: rows of ``feedback``, only inserted.

The functions run inside a transaction of :class:`~brevia.db.store.SqlStore`.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import RowMapping, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from brevia.db.tables import feedback, runs
from brevia.errors import Unavailable

FeedbackKind = Literal["correction", "rating"]
Rating = Literal["good", "bad"]
FeedbackSource = Literal["user", "reviewer", "automatic"]


@dataclass(frozen=True)
class RunOwner:
    """The caller that created a run; ``None`` for trusted code in the process."""

    caller: str | None


@dataclass(frozen=True)
class FeedbackRecord:
    """Feedback on a run, as recorded."""

    id: uuid.UUID
    run_id: uuid.UUID
    kind: FeedbackKind
    source: FeedbackSource
    items: Sequence[Mapping[str, Any]]
    rating: Rating | None
    comment: str | None
    external_ref: Mapping[str, Any] | None
    created_at: datetime
    caller: str | None = None  # None for trusted code in the process
    end_user: str | None = None
    idempotency_key: str | None = None


def _record(row: RowMapping) -> FeedbackRecord:
    return FeedbackRecord(
        id=row["id"],
        run_id=row["run_id"],
        kind=row["kind"],
        source=row["source"],
        items=row["items"],
        rating=row["rating"],
        comment=row["comment"],
        external_ref=row["external_ref"],
        created_at=row["created_at"],
        caller=row["caller"],
        end_user=row["end_user"],
        idempotency_key=row["idempotency_key"],
    )


async def owner(connection: AsyncConnection, run_id: uuid.UUID) -> RunOwner | None:
    """The owner of the run ``run_id``, direct or job, or ``None`` when there is no
    such run."""
    row = (
        await connection.execute(select(runs.c.caller).where(runs.c.id == run_id))
    ).first()
    return None if row is None else RunOwner(row[0])


async def find(
    connection: AsyncConnection,
    caller: str | None,
    run_id: uuid.UUID,
    idempotency_key: str,
) -> FeedbackRecord | None:
    """The feedback that ``caller`` added to ``run_id`` with ``idempotency_key``."""
    row = (
        (
            await connection.execute(
                select(feedback).where(
                    feedback.c.caller.is_not_distinct_from(caller),
                    feedback.c.run_id == run_id,
                    feedback.c.idempotency_key == idempotency_key,
                )
            )
        )
        .mappings()
        .first()
    )
    return None if row is None else _record(row)


async def add(
    connection: AsyncConnection, record: FeedbackRecord
) -> tuple[FeedbackRecord, bool]:
    """Record feedback on a run, or return the feedback recorded with the same
    idempotency key by the same caller on the same run.

    Returns the record and whether it was created now. A concurrent submission with
    the same key waits for this one and then finds it.
    """
    statement = pg_insert(feedback).values(
        id=record.id,
        run_id=record.run_id,
        kind=record.kind,
        source=record.source,
        items=list(record.items),
        rating=record.rating,
        comment=record.comment,
        external_ref=record.external_ref,
        caller=record.caller,
        end_user=record.end_user,
        idempotency_key=record.idempotency_key,
        created_at=record.created_at,
    )
    key = record.idempotency_key
    if key is not None:
        statement = statement.on_conflict_do_nothing(
            index_elements=["caller", "run_id", "idempotency_key"],
            index_where=feedback.c.idempotency_key.is_not(None),
        )
    inserted = (await connection.execute(statement.returning(feedback.c.id))).first()
    if inserted is not None:
        return record, True
    existing = (
        None
        if key is None
        else await find(connection, record.caller, record.run_id, key)
    )
    if existing is None:
        raise Unavailable("The feedback of the idempotency key cannot be read")
    return existing, False
