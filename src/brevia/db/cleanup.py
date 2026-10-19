"""Deletion of expired contents of model calls (specification §7.8, §11.5).

Expired contents are cleared, not removed: the row of ``trace_contents`` keeps its
expiry and the time of the deletion, so that a reader can tell that the contents
existed and expired. Metrics and usage of the calls stay.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from brevia.db.tables import trace_contents

BATCH = 1000
"""Rows cleared in one transaction."""


def _expired(now: datetime) -> ColumnElement[bool]:
    """Expired and not cleared. Contents are written with the outcome of their run,
    so they always belong to a run that has ended."""
    return (trace_contents.c.expires_at <= now) & trace_contents.c.deleted_at.is_(None)


async def count_expired(connection: AsyncConnection, now: datetime) -> int:
    """Contents expired at ``now`` and not yet cleared."""
    return (
        await connection.execute(
            select(func.count()).select_from(trace_contents).where(_expired(now))
        )
    ).scalar_one()


async def clear_expired(connection: AsyncConnection, now: datetime) -> int:
    """Clear at most :data:`BATCH` expired contents; returns how many."""
    batch = (
        select(trace_contents.c.call_id)
        .where(_expired(now))
        .limit(BATCH)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    cleared = await connection.execute(
        update(trace_contents)
        .where(trace_contents.c.call_id.in_(batch))
        .values(instructions=None, user_text=None, output=None, deleted_at=now)
    )
    return cleared.rowcount
