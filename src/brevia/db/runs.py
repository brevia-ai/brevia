"""Records of runs: their rows in ``runs``, their model calls and call contents.

The functions run inside a transaction of :class:`~brevia.db.store.SqlStore`. Jobs
have their own functions in :mod:`brevia.db.jobs`; their outcome and model calls are
written here, as those of a direct run.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import ColumnElement, and_, exists, insert, update
from sqlalchemy.ext.asyncio import AsyncConnection

from brevia.db.jobs import ACTIVE
from brevia.db.tables import model_calls, runs, trace_contents
from brevia.models.limits import CallUsage

RunStatus = Literal["running", "succeeded", "failed", "cancelled"]


@dataclass(frozen=True)
class NewRun:
    """A run at its start."""

    id: uuid.UUID
    activity: str
    activity_version: str
    mode: Literal["direct", "job"]
    input: Mapping[str, Any]
    snapshot: Mapping[str, Any]
    started_at: datetime
    caller: str | None = None  # None for trusted code in the process
    end_user: str | None = None


@dataclass(frozen=True)
class RunOutcome:
    """The end of a run: its status and its result or error, with its usage.

    ``adapter`` names the model adapter of the run: ``fake`` when a fake answered
    any of its calls. Each call records the adapter that made it.
    ``contents_expire_at`` is ``None`` when no contents were captured or when they
    are kept without a time limit (``retention_days`` 0).
    """

    id: uuid.UUID
    status: RunStatus
    result: Mapping[str, Any] | None
    error: Mapping[str, Any] | None
    usage: Mapping[str, Any]
    calls: Sequence[CallUsage]
    adapter: Mapping[str, str]
    finished_at: datetime
    contents_expire_at: datetime | None = None


async def create(connection: AsyncConnection, run: NewRun) -> None:
    """Record a run at its start."""
    await connection.execute(
        insert(runs).values(
            id=run.id,
            caller=run.caller,
            end_user=run.end_user,
            activity=run.activity,
            activity_version=run.activity_version,
            mode=run.mode,
            status="running",
            input=run.input,
            snapshot=run.snapshot,
            created_at=run.started_at,
            started_at=run.started_at,
        )
    )


async def finish(connection: AsyncConnection, outcome: RunOutcome) -> None:
    """Record the outcome of a run with its model calls (see
    :meth:`brevia.db.store.Store.finish_run`)."""
    # A run that has not ended takes the outcome. A cancelled outcome ends
    # only a direct run: for a job it comes from a stop of the worker, and
    # the job starts again.
    active: ColumnElement[bool] = runs.c.status.in_(ACTIVE)
    if outcome.status == "cancelled":
        active = and_(active, runs.c.mode == "direct")
    ended = await connection.execute(
        update(runs)
        .where(runs.c.id == outcome.id, active)
        .values(
            status=outcome.status,
            result=outcome.result,
            error=outcome.error,
            usage=outcome.usage,
            finished_at=outcome.finished_at,
        )
    )
    if not ended.rowcount:
        # A job cancelled meanwhile keeps its status and receives the usage
        # and the calls of the run, unless its calls are already recorded.
        # Any other run has ended already: nothing is written.
        recorded = exists().where(model_calls.c.run_id == outcome.id)
        cancelled = await connection.execute(
            update(runs)
            .where(
                runs.c.id == outcome.id,
                runs.c.status == "cancelled",
                ~recorded,
            )
            .values(usage=outcome.usage)
        )
        if not cancelled.rowcount:
            return
    await insert_calls(connection, outcome)


def call_row(run_id: uuid.UUID, sequence: int, call: CallUsage) -> dict[str, Any]:
    """Columns of a ``model_calls`` row, without the adapter."""
    return {
        "run_id": run_id,
        "sequence": sequence,
        "model": call.model,
        "options": call.options,
        "request_records": [r.model_dump(mode="json") for r in call.request_records],
        "requests": call.requests,
        "tool_calls": call.tool_calls,
        "input_tokens": call.input_tokens,
        "output_tokens": call.output_tokens,
        "cache_read_tokens": call.cache_read_tokens,
        "cache_write_tokens": call.cache_write_tokens,
        "cost_usd": call.cost_usd,
        "prices": None if call.prices is None else call.prices.model_dump(mode="json"),
        "seconds": call.seconds,
        "error": call.error,
        "started_at": call.started_at,
    }


async def insert_calls(connection: AsyncConnection, outcome: RunOutcome) -> None:
    """Insert the model calls of a run and their captured contents, if any."""
    if not outcome.calls:
        return

    def adapter(call: CallUsage) -> dict[str, str]:
        made_by = call.adapter or outcome.adapter
        return {"adapter": made_by["name"], "adapter_version": made_by["version"]}

    ids = (
        await connection.execute(
            insert(model_calls).returning(
                model_calls.c.id, sort_by_parameter_order=True
            ),
            [
                {**call_row(outcome.id, sequence, call), **adapter(call)}
                for sequence, call in enumerate(outcome.calls)
            ],
        )
    ).scalars()
    contents = [
        {
            "call_id": call_id,
            "instructions": call.content.instructions,
            "user_text": call.content.user_text,
            "output": call.content.output,
            "expires_at": outcome.contents_expire_at,
        }
        for call_id, call in zip(ids, outcome.calls, strict=True)
        if call.content is not None
    ]
    if contents:
        await connection.execute(insert(trace_contents), contents)
