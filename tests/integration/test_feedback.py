"""Feedback on runs on PostgreSQL: idempotency through JSONB and under concurrency."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from brevia import Brevia, Caller, IdempotencyConflict
from brevia.db import migrate
from brevia.db.engine import sync_engine
from brevia.db.runs import NewRun
from brevia.db.tables import SCHEMA, feedback
from integration.support import answering_brevia, settings_for

pytestmark = pytest.mark.integration

CALLER = Caller("backend", end_user="user-7")
CORRECTION = {
    "kind": "correction",
    "items": [
        {"target": "summary", "original": "Breve.", "corrected": "Breve e chiaro."},
        {"target": "title", "original": "Titolo", "corrected": "Titolo nuovo"},
    ],
    "comment": "Più chiaro.",
    "external_ref": {"system": "bedita", "object_id": "42", "revision": "3"},
}


@pytest.fixture
async def app(database_url: str, schema: str, tmp_path: Path) -> AsyncIterator[Brevia]:
    migrate.upgrade(database_url, schema)
    brevia = answering_brevia(tmp_path, settings_for(database_url, schema))
    await brevia.start()
    try:
        yield brevia
    finally:
        await brevia.stop()


async def recorded_run(app: Brevia) -> str:
    """A recorded direct run of ``CALLER``, written through the store."""
    run_id = uuid.uuid4()
    await app._store.create_run(
        NewRun(
            id=run_id,
            activity="test.answer",
            activity_version="1",
            mode="direct",
            input={"text": "q"},
            snapshot={"format": 2},
            started_at=datetime.now(UTC),
            caller=CALLER.name,
            end_user=CALLER.end_user,
        )
    )
    return str(run_id)


def feedback_count(database_url: str, schema: str) -> int:
    engine = sync_engine(database_url)
    try:
        with engine.connect() as connection:
            connection = connection.execution_options(
                schema_translate_map={SCHEMA: schema}
            )
            count: int = connection.execute(
                select(func.count()).select_from(feedback)
            ).scalar_one()
            return count
    finally:
        engine.dispose()


async def test_a_repeated_correction_read_back_from_jsonb_is_not_a_conflict(
    app: Brevia, database_url: str, schema: str
) -> None:
    run_id = await recorded_run(app)
    first = await app.add_feedback(
        run_id, CORRECTION, idempotency_key="k", caller=CALLER
    )
    again = await app.add_feedback(
        run_id, CORRECTION, idempotency_key="k", caller=CALLER
    )
    assert again == first
    with pytest.raises(IdempotencyConflict):
        await app.add_feedback(
            run_id,
            CORRECTION | {"comment": "Diverso."},
            idempotency_key="k",
            caller=CALLER,
        )
    assert feedback_count(database_url, schema) == 1


async def test_concurrent_submissions_with_one_key_give_one_feedback(
    app: Brevia, database_url: str, schema: str
) -> None:
    run_id = await recorded_run(app)
    results = await asyncio.gather(
        *(
            app.add_feedback(run_id, CORRECTION, idempotency_key="same", caller=CALLER)
            for _ in range(5)
        )
    )
    assert len({result.id for result in results}) == 1
    assert all(result == results[0] for result in results)
    assert feedback_count(database_url, schema) == 1
