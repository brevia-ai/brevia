"""Feedback on runs: corrections and ratings, only added, with access by caller."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from conftest import answers, project_brevia, simulated
from memory_store import MemoryStore

from brevia import (
    AccessPolicy,
    Brevia,
    Caller,
    Correction,
    FeedbackRequest,
    IdempotencyConflict,
    InvalidInput,
    NotFound,
)

pytestmark = pytest.mark.unit

OWNER = Caller("backend", end_user="user-7")
CORRECTION = {
    "kind": "correction",
    "items": [
        {"target": "summary", "original": "Breve.", "corrected": "Breve e chiaro."}
    ],
    "external_ref": {"system": "bedita", "object_id": "42", "revision": "3"},
}


async def direct_run(app: Brevia, store: MemoryStore, caller: Caller | None) -> str:
    """Identifier of a recorded direct run of ``caller``."""
    with simulated(answers({"summary": "Breve."})):
        await app.run("document.summarize", {"text": "Un testo."}, caller=caller)
    return str(list(store.runs)[-1])


async def test_corrections_are_recorded_with_their_caller(
    brevia: Brevia, store: MemoryStore
) -> None:
    run_id = await direct_run(brevia, store, OWNER)
    feedback = await brevia.add_feedback(run_id, CORRECTION, caller=OWNER)

    assert feedback.run_id == run_id
    assert feedback.kind == "correction"
    assert feedback.items == [
        Correction(target="summary", original="Breve.", corrected="Breve e chiaro.")
    ]
    assert (feedback.caller, feedback.end_user) == ("backend", "user-7")
    (record,) = store.feedback
    assert str(record.id) == feedback.id
    assert record.run_id == uuid.UUID(run_id)
    assert record.items == [
        {"target": "summary", "original": "Breve.", "corrected": "Breve e chiaro."}
    ]
    assert record.external_ref == CORRECTION["external_ref"]
    assert (record.caller, record.end_user) == ("backend", "user-7")


async def test_feedback_is_only_added(brevia: Brevia, store: MemoryStore) -> None:
    run_id = await direct_run(brevia, store, None)
    first = await brevia.add_feedback(run_id, CORRECTION)
    rating = FeedbackRequest(kind="rating", rating="bad", comment="Troppo breve.")
    second = await brevia.add_feedback(run_id, rating)
    assert [record.kind for record in store.feedback] == ["correction", "rating"]
    assert first.id != second.id
    assert (second.rating, second.comment, second.items) == ("bad", "Troppo breve.", [])
    assert (second.caller, second.end_user) == (None, None)  # trusted code
    # The output of the run is not changed.
    assert store.only_outcome().result == {"summary": "Breve."}


@pytest.mark.parametrize(
    "feedback",
    [
        {"kind": "correction", "items": []},
        {"kind": "correction", "items": CORRECTION["items"], "rating": "good"},
        {"kind": "rating"},
        {"kind": "rating", "rating": "good", "items": CORRECTION["items"]},
        {"kind": "rating", "rating": "excellent"},
        {"kind": "opinion", "comment": "x"},
        {"kind": "rating", "rating": "good", "score": 5},
        {"kind": "rating", "rating": "good", "external_ref": {"object_id": 42}},
        {
            "kind": "correction",
            "items": [{"target": "", "original": "a", "corrected": "b"}],
        },
    ],
)
async def test_invalid_feedback_is_refused(
    brevia: Brevia, store: MemoryStore, feedback: dict[str, Any]
) -> None:
    run_id = await direct_run(brevia, store, None)
    with pytest.raises(InvalidInput) as raised:
        await brevia.add_feedback(run_id, feedback)
    assert "errors" in raised.value.details
    assert store.feedback == []


async def test_a_nul_character_is_refused_without_its_value(
    brevia: Brevia, store: MemoryStore
) -> None:
    run_id = await direct_run(brevia, store, None)
    rating = {"kind": "rating", "rating": "good", "comment": "secret\x00value"}
    with pytest.raises(InvalidInput) as raised:
        await brevia.add_feedback(run_id, rating)
    assert "secret" not in str(raised.value)
    assert raised.value.details == {}
    assert store.feedback == []


async def test_feedback_needs_a_recorded_run_the_caller_may_see(
    tmp_path: Path, store: MemoryStore
) -> None:
    policy = AccessPolicy(admins=frozenset({"admin"}))
    async with project_brevia(tmp_path, store, access=policy) as app:
        run_id = await direct_run(app, store, OWNER)
        rating = {"kind": "rating", "rating": "good"}
        for missing in (str(uuid.uuid4()), "not-a-run"):
            with pytest.raises(NotFound):
                await app.add_feedback(missing, rating)
        with pytest.raises(NotFound):
            await app.add_feedback(run_id, rating, caller=Caller("other"))
        assert store.feedback == []
        await app.add_feedback(run_id, rating, caller=Caller("admin"))
        await app.add_feedback(run_id, rating, caller=OWNER)
        assert [record.caller for record in store.feedback] == ["admin", "backend"]


async def test_feedback_is_refused_before_the_run_is_read(
    brevia: Brevia, store: MemoryStore
) -> None:
    store.fail.add("run_owner")
    with pytest.raises(InvalidInput):
        await brevia.add_feedback(str(uuid.uuid4()), {"kind": "rating"})


async def test_trusted_code_and_the_shared_policy_reach_every_run(
    tmp_path: Path, store: MemoryStore
) -> None:
    rating = {"kind": "rating", "rating": "good"}
    async with project_brevia(tmp_path, store) as app:
        run_id = await direct_run(app, store, OWNER)
        await app.add_feedback(run_id, rating)  # trusted code, no caller
    async with project_brevia(tmp_path, store, access=AccessPolicy(shared=True)) as app:
        await app.add_feedback(run_id, rating, caller=Caller("other"))
    assert [record.caller for record in store.feedback] == [None, "other"]


async def test_an_instance_changed_after_its_creation_is_validated_again(
    brevia: Brevia, store: MemoryStore
) -> None:
    run_id = await direct_run(brevia, store, None)
    correction = FeedbackRequest.model_validate(CORRECTION)
    correction.items.clear()  # frozen does not freeze the list
    with pytest.raises(InvalidInput):
        await brevia.add_feedback(run_id, correction)
    assert store.feedback == []


# ---------- source and idempotency ----------


async def test_the_source_is_the_end_user_unless_given(
    brevia: Brevia, store: MemoryStore
) -> None:
    run_id = await direct_run(brevia, store, None)
    by_default = await brevia.add_feedback(run_id, CORRECTION)
    review = await brevia.add_feedback(
        run_id, {"kind": "rating", "rating": "bad", "source": "reviewer"}
    )
    assert (by_default.source, review.source) == ("user", "reviewer")
    assert [record.source for record in store.feedback] == ["user", "reviewer"]
    with pytest.raises(InvalidInput):
        await brevia.add_feedback(
            run_id, {"kind": "rating", "rating": "bad", "source": "robot"}
        )


async def test_a_repeated_submission_with_a_key_is_recorded_once(
    brevia: Brevia, store: MemoryStore
) -> None:
    run_id = await direct_run(brevia, store, OWNER)
    first = await brevia.add_feedback(
        run_id, CORRECTION, idempotency_key="doc-42-v3", caller=OWNER
    )
    again = await brevia.add_feedback(
        run_id, CORRECTION, idempotency_key="doc-42-v3", caller=OWNER
    )
    assert again == first
    assert len(store.feedback) == 1
    # The same key from another caller is another feedback.
    await brevia.add_feedback(run_id, CORRECTION, idempotency_key="doc-42-v3")
    assert len(store.feedback) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"comment": "Different."},
        {"source": "reviewer"},
        {"external_ref": {"system": "bedita", "object_id": "43"}},
    ],
)
async def test_a_key_used_for_different_feedback_is_refused(
    brevia: Brevia, store: MemoryStore, change: dict[str, Any]
) -> None:
    run_id = await direct_run(brevia, store, OWNER)
    first = await brevia.add_feedback(
        run_id, CORRECTION, idempotency_key="k", caller=OWNER
    )
    with pytest.raises(IdempotencyConflict) as raised:
        await brevia.add_feedback(
            run_id, CORRECTION | change, idempotency_key="k", caller=OWNER
        )
    assert raised.value.details == {"feedback_id": first.id}
    assert len(store.feedback) == 1


async def test_a_key_with_another_end_user_is_refused(
    brevia: Brevia, store: MemoryStore
) -> None:
    run_id = await direct_run(brevia, store, OWNER)
    await brevia.add_feedback(run_id, CORRECTION, idempotency_key="k", caller=OWNER)
    with pytest.raises(IdempotencyConflict):
        await brevia.add_feedback(
            run_id,
            CORRECTION,
            idempotency_key="k",
            caller=Caller("backend", end_user="user-8"),
        )


@pytest.mark.parametrize("key", ["", " ", "k" * 201, "k\x00"])
async def test_an_invalid_key_is_refused(
    brevia: Brevia, store: MemoryStore, key: str
) -> None:
    run_id = await direct_run(brevia, store, None)
    with pytest.raises(InvalidInput):
        await brevia.add_feedback(run_id, CORRECTION, idempotency_key=key)
    assert store.feedback == []
