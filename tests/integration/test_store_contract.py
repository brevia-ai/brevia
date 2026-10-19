"""The behaviour of every store (``tests/store_contract.py``) on PostgreSQL."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select

from brevia import Unavailable
from brevia.db import migrate
from brevia.db.engine import sync_engine
from brevia.db.feedback import FeedbackRecord
from brevia.db.store import SqlStore
from brevia.db.tables import SCHEMA, feedback
from integration.support import settings_for
from store_contract import *  # noqa: F403  (the tests of the contract)

pytestmark = pytest.mark.integration


@pytest.fixture
async def contract_store(database_url: str, schema: str) -> AsyncIterator[SqlStore]:
    migrate.upgrade(database_url, schema)
    store = SqlStore(settings_for(database_url, schema))
    await store.start()
    try:
        yield store
    finally:
        await store.stop()


async def test_feedback_is_stored_as_given(
    contract_store: SqlStore, database_url: str, schema: str
) -> None:
    run = direct_run()  # noqa: F405
    await contract_store.create_run(run)
    record = FeedbackRecord(
        id=uuid.uuid4(),
        run_id=run.id,
        kind="correction",
        source="user",
        items=[{"target": "summary", "original": "a", "corrected": "b"}],
        rating=None,
        comment="ok",
        external_ref={"system": "bedita", "object_id": "42"},
        created_at=NOW,  # noqa: F405
        caller="one",
        end_user="user-7",
    )
    await contract_store.add_feedback(record)
    reader = sync_engine(database_url)
    try:
        with reader.connect() as connection:
            connection = connection.execution_options(
                schema_translate_map={SCHEMA: schema}
            )
            (row,) = connection.execute(select(feedback)).mappings().all()
    finally:
        reader.dispose()
    assert dict(row) == {
        "id": record.id,
        "run_id": run.id,
        "kind": "correction",
        "items": [{"target": "summary", "original": "a", "corrected": "b"}],
        "rating": None,
        "comment": "ok",
        "external_ref": {"system": "bedita", "object_id": "42"},
        "caller": "one",
        "source": "user",
        "end_user": "user-7",
        "idempotency_key": None,
        "created_at": NOW,  # noqa: F405
    }


async def test_feedback_on_a_missing_run_is_refused(contract_store: SqlStore) -> None:
    record = FeedbackRecord(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        kind="rating",
        source="user",
        items=[],
        rating="good",
        comment=None,
        external_ref=None,
        created_at=NOW,  # noqa: F405
    )
    with pytest.raises(Unavailable):
        await contract_store.add_feedback(record)
