"""Behaviour every store must have, run on the store in memory and on PostgreSQL.

The unit tests check the application against :class:`MemoryStore`; these tests check
that it behaves as :class:`~brevia.db.store.SqlStore` does, through the operations of
:class:`~brevia.db.store.Store` only. A module that imports them provides the
``contract_store`` fixture, a started store with an empty database.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Connection

from brevia import VersionConflict
from brevia.db.feedback import FeedbackRecord, RunOwner
from brevia.db.jobs import JobQuery, NewJob
from brevia.db.runs import NewRun, RunOutcome
from brevia.db.store import Store
from brevia.models.limits import CallUsage

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
ADAPTER = {"name": "pydantic-ai", "version": "2.55.0"}
SNAPSHOT = {"format": 2, "config": {"language": "it"}}
NO_USAGE = {
    "requests": 0,
    "tool_calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "cost_usd": "0",
    "cost_kind": "estimate",
}


class Queue:
    """Records the jobs queued by a submission."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, connection: Connection | None) -> None:
        self.calls += 1


def new_job(
    activity: str = "test.job", key: str | None = None, caller: str | None = None
) -> NewJob:
    return NewJob(
        id=uuid.uuid4(),
        activity=activity,
        activity_version="1",
        input={"text": "eco"},
        overrides={},
        idempotency_key=key,
        fingerprint="f",
        retry_of_run_id=None,
        created_at=NOW,
        caller=caller,
        end_user=None if caller is None else "user-7",
    )


def direct_run() -> NewRun:
    return NewRun(
        id=uuid.uuid4(),
        activity="test.one",
        activity_version="1",
        mode="direct",
        input={"text": "eco"},
        snapshot=SNAPSHOT,
        started_at=NOW,
        caller="one",
    )


def call(cost: Decimal | None = Decimal("0.00012")) -> CallUsage:
    return CallUsage(
        model="openai:test-model",
        options={},
        started_at=NOW,
        requests=1,
        tool_calls=0,
        input_tokens=100,
        output_tokens=10,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=cost,
        prices=None,
        seconds=0.5,
    )


def outcome(
    run_id: uuid.UUID,
    status: Any,
    *,
    calls: tuple[CallUsage, ...] = (),
    result: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
) -> RunOutcome:
    usage = {**NO_USAGE, "requests": len(calls), "input_tokens": 100 * len(calls)}
    return RunOutcome(
        id=run_id,
        status=status,
        result=result,
        error=error,
        usage=usage,
        calls=calls,
        adapter=ADAPTER,
        finished_at=NOW + timedelta(seconds=5),
    )


async def started(store: Store, key: str | None = None) -> uuid.UUID:
    """A job submitted and started."""
    job = new_job(key=key)
    await store.submit_job(job, Queue())
    await store.start_job(job.id, SNAPSHOT, NOW, NOW + timedelta(minutes=15))
    return job.id


# ---------- submission ----------


async def test_a_started_store_passes_its_check(contract_store: Store) -> None:
    await contract_store.check()


async def test_a_submission_records_and_queues_a_job(contract_store: Store) -> None:
    job, queue = new_job(), Queue()
    record, created = await contract_store.submit_job(job, queue)
    assert created
    assert queue.calls == 1
    assert record.status == "queued"
    assert record.snapshot is None
    assert record.started_at is None
    assert await contract_store.job(job.id) == record


async def test_an_unknown_job_is_none(contract_store: Store) -> None:
    assert await contract_store.job(uuid.uuid4()) is None
    assert await contract_store.find_job(None, "test.job", "missing") is None


async def test_the_same_key_gives_the_job_already_recorded(
    contract_store: Store,
) -> None:
    first, queue = new_job(key="k"), Queue()
    await contract_store.submit_job(first, queue)
    record, created = await contract_store.submit_job(new_job(key="k"), queue)
    assert not created
    assert record.id == first.id
    assert queue.calls == 1  # the second submission queues nothing
    found = await contract_store.find_job(None, "test.job", "k")
    assert found is not None
    assert found.id == first.id


async def test_a_key_is_scoped_to_its_activity(contract_store: Store) -> None:
    await contract_store.submit_job(new_job("test.one", "k"), Queue())
    other = new_job("test.two", "k")
    record, created = await contract_store.submit_job(other, Queue())
    assert created
    assert record.id == other.id


async def test_a_submission_records_its_caller(contract_store: Store) -> None:
    job = new_job(caller="backend")
    record, _ = await contract_store.submit_job(job, Queue())
    assert (record.caller, record.end_user) == ("backend", "user-7")
    assert await contract_store.job(job.id) == record


async def test_a_key_is_scoped_to_its_caller(contract_store: Store) -> None:
    jobs = [new_job(key="k", caller=name) for name in ("one", "two", None)]
    for job in jobs:
        record, created = await contract_store.submit_job(job, Queue())
        assert created
        assert record.id == job.id
    for job in jobs:
        found = await contract_store.find_job(job.caller, "test.job", "k")
        assert found is not None
        assert found.id == job.id
    assert await contract_store.find_job("three", "test.job", "k") is None
    again = new_job(key="k", caller="one")
    record, created = await contract_store.submit_job(again, Queue())
    assert not created
    assert record.id == jobs[0].id


# ---------- list ----------


async def test_jobs_are_listed_newest_first_with_filters(
    contract_store: Store,
) -> None:
    jobs = [
        replace(new_job(activity, key, caller), created_at=NOW + timedelta(minutes=i))
        for i, (activity, key, caller) in enumerate(
            [
                ("test.one", "a", "one"),
                ("test.two", None, "one"),
                ("test.one", None, "two"),
                ("test.one", "a", None),
            ]
        )
    ]
    for job in jobs:
        await contract_store.submit_job(job, Queue())
    await contract_store.create_run(direct_run())  # not a job: never listed
    await contract_store.start_job(
        jobs[0].id, SNAPSHOT, NOW, NOW + timedelta(minutes=15)
    )

    async def ids(**filters: Any) -> list[uuid.UUID]:
        found = await contract_store.list_jobs(JobQuery(limit=10, **filters))
        return [record.id for record in found]

    every = [job.id for job in reversed(jobs)]
    assert await ids() == every
    assert await ids(owner="one") == [jobs[1].id, jobs[0].id]
    assert await ids(activity="test.one") == [jobs[3].id, jobs[2].id, jobs[0].id]
    assert await ids(statuses=("running",)) == [jobs[0].id]
    assert await ids(statuses=("queued", "running")) == every
    assert await ids(idempotency_key="a") == [jobs[3].id, jobs[0].id]
    assert await ids(owner="three") == []


async def test_a_page_starts_after_the_last_job_of_the_previous(
    contract_store: Store,
) -> None:
    # The same creation time for two jobs: the identifier orders them.
    jobs = [new_job() for _ in range(3)]
    jobs[2] = replace(jobs[2], created_at=NOW + timedelta(seconds=1))
    for job in jobs:
        await contract_store.submit_job(job, Queue())
    first = await contract_store.list_jobs(JobQuery(limit=2))
    last = first[-1]
    rest = await contract_store.list_jobs(
        JobQuery(limit=2, after=(last.created_at, last.id))
    )
    listed = [record.id for record in first + rest]
    assert sorted(listed) == sorted(job.id for job in jobs)
    assert listed[0] == jobs[2].id
    assert len(rest) == 1


# ---------- feedback ----------


async def test_the_owner_of_a_run_is_found_for_direct_runs_and_jobs(
    contract_store: Store,
) -> None:
    run = direct_run()
    await contract_store.create_run(run)
    job = new_job(caller="backend")
    await contract_store.submit_job(job, Queue())
    trusted = new_job()
    await contract_store.submit_job(trusted, Queue())
    assert await contract_store.run_owner(run.id) == RunOwner("one")
    assert await contract_store.run_owner(job.id) == RunOwner("backend")
    assert await contract_store.run_owner(trusted.id) == RunOwner(None)
    assert await contract_store.run_owner(uuid.uuid4()) is None


async def test_feedback_is_recorded_on_a_run(contract_store: Store) -> None:
    run = direct_run()
    await contract_store.create_run(run)
    for kind, items, rating in (
        ("correction", [{"target": "t", "original": "a", "corrected": "b"}], None),
        ("rating", [], "good"),
    ):
        record = FeedbackRecord(
            id=uuid.uuid4(),
            run_id=run.id,
            kind=kind,  # type: ignore[arg-type]
            source="user",
            items=items,
            rating=rating,  # type: ignore[arg-type]
            comment="ok",
            external_ref={"system": "bedita", "object_id": "42"},
            created_at=NOW,
            caller="one",
            end_user="user-7",
        )
        assert await contract_store.add_feedback(record) == (record, True)


def rating(run_id: uuid.UUID, caller: str | None, key: str | None) -> FeedbackRecord:
    return FeedbackRecord(
        id=uuid.uuid4(),
        run_id=run_id,
        kind="rating",
        source="reviewer",
        items=[],
        rating="good",
        comment=None,
        external_ref=None,
        created_at=NOW,
        caller=caller,
        idempotency_key=key,
    )


async def test_the_same_key_gives_the_feedback_already_recorded(
    contract_store: Store,
) -> None:
    run = direct_run()
    await contract_store.create_run(run)
    first = rating(run.id, "one", "k")
    assert await contract_store.add_feedback(first) == (first, True)
    stored, created = await contract_store.add_feedback(rating(run.id, "one", "k"))
    assert not created
    assert stored == first
    # Another caller, trusted code or no key: new feedback.
    for caller, key in (("two", "k"), (None, "k"), ("one", None), ("one", None)):
        _, created = await contract_store.add_feedback(rating(run.id, caller, key))
        assert created
    _, created = await contract_store.add_feedback(rating(run.id, None, "k"))
    assert not created


# ---------- start ----------


async def test_a_start_records_the_snapshot_and_keeps_the_first_times(
    contract_store: Store,
) -> None:
    job = new_job()
    await contract_store.submit_job(job, Queue())
    deadline = NOW + timedelta(minutes=15)
    first = await contract_store.start_job(job.id, SNAPSHOT, NOW, deadline)
    assert first is not None
    assert first.status == "running"
    assert first.snapshot == SNAPSHOT
    assert (first.started_at, first.deadline_at) == (NOW, deadline)
    # A step run again keeps the first start and deadline.
    later = NOW + timedelta(minutes=1)
    again = await contract_store.start_job(
        job.id, SNAPSHOT, later, later + timedelta(minutes=15)
    )
    assert again is not None
    assert (again.started_at, again.deadline_at) == (NOW, deadline)


async def test_an_ended_job_does_not_start(contract_store: Store) -> None:
    job = new_job()
    await contract_store.submit_job(job, Queue())
    assert await contract_store.finish_job(job.id, "cancelled", None, {}, NOW)
    assert await contract_store.start_job(job.id, SNAPSHOT, NOW, NOW) is None
    record = await contract_store.job(job.id)
    assert record is not None
    assert record.status == "cancelled"
    assert record.started_at is None


# ---------- end ----------


async def test_an_outcome_ends_a_running_job(contract_store: Store) -> None:
    run_id = await started(contract_store)
    await contract_store.finish_run(
        outcome(run_id, "succeeded", calls=(call(),), result={"summary": "ok"})
    )
    record = await contract_store.job(run_id)
    assert record is not None
    assert record.status == "succeeded"
    assert record.result == {"summary": "ok"}
    assert record.usage is not None
    assert record.usage["requests"] == 1
    assert record.finished_at == NOW + timedelta(seconds=5)
    # The end is written once.
    assert not await contract_store.finish_job(run_id, "failed", None, {}, NOW)
    await contract_store.finish_run(outcome(run_id, "failed", error={"code": "x"}))
    assert await contract_store.job(run_id) == record


async def test_a_cancelled_outcome_of_a_running_job_is_not_written(
    contract_store: Store,
) -> None:
    # It comes from a stop of the worker: the job starts again.
    run_id = await started(contract_store)
    await contract_store.finish_run(outcome(run_id, "cancelled", calls=(call(),)))
    record = await contract_store.job(run_id)
    assert record is not None
    assert record.status == "running"
    assert record.usage is None


async def test_a_job_cancelled_meanwhile_receives_the_calls_once(
    contract_store: Store,
) -> None:
    run_id = await started(contract_store)
    assert await contract_store.finish_job(
        run_id, "cancelled", None, {"code": "cancelled"}, NOW
    )
    cancelled = await contract_store.job(run_id)
    assert cancelled is not None
    assert cancelled.usage == NO_USAGE  # no calls recorded yet

    await contract_store.finish_run(outcome(run_id, "succeeded", calls=(call(),)))
    record = await contract_store.job(run_id)
    assert record is not None
    assert record.status == "cancelled"
    assert record.error == {"code": "cancelled"}
    assert record.result is None
    assert record.usage is not None
    assert record.usage["requests"] == 1

    # A second outcome finds the calls recorded and adds nothing.
    await contract_store.finish_run(outcome(run_id, "failed", calls=(call(), call())))
    assert await contract_store.job(run_id) == record


# ---------- customisations ----------


async def test_configuration_changes_take_one_version_each(
    contract_store: Store,
) -> None:
    empty = await contract_store.customizations("test.job")
    assert empty.configuration.version == 0
    assert empty.configuration.values == {}

    first = await contract_store.save_configuration(
        "test.job",
        lambda current: {**current, "language": "it"},
        expected_version=0,
        author="ada",
        now=NOW,
    )
    assert (first.version, first.values, first.updated_by) == (
        1,
        {"language": "it"},
        "ada",
    )
    second = await contract_store.save_configuration(
        "test.job",
        lambda current: {**current, "length": 3},
        expected_version=None,
        author=None,
        now=NOW,
    )
    assert second.version == 2
    assert second.values == {"language": "it", "length": 3}
    read = await contract_store.customizations("test.job")
    assert read.configuration == second


async def test_a_stale_version_is_refused(contract_store: Store) -> None:
    await contract_store.save_configuration(
        "test.job", lambda _: {"a": 1}, expected_version=None, author=None, now=NOW
    )
    with pytest.raises(VersionConflict):
        await contract_store.save_configuration(
            "test.job", lambda _: {"a": 2}, expected_version=0, author=None, now=NOW
        )
    read = await contract_store.customizations("test.job")
    assert read.configuration.values == {"a": 1}


async def test_prompt_changes_keep_a_history(contract_store: Store) -> None:
    saved = await contract_store.save_prompt(
        "test.job",
        "summary",
        "Riassumi.",
        operation="customize",
        sha256="s1",
        expected_version=0,
        author="ada",
        now=NOW,
    )
    assert saved.version == 1
    reset = await contract_store.save_prompt(
        "test.job",
        "summary",
        None,
        operation="reset",
        sha256=None,
        expected_version=1,
        author=None,
        now=NOW + timedelta(minutes=1),
    )
    assert (reset.version, reset.text) == (2, None)
    with pytest.raises(VersionConflict):
        await contract_store.save_prompt(
            "test.job",
            "summary",
            "Tardi.",
            operation="customize",
            sha256="s3",
            expected_version=1,
            author=None,
            now=NOW,
        )
    history = await contract_store.prompt_history("test.job", "summary")
    assert [(r.version, r.operation, r.text, r.sha256) for r in history] == [
        (2, "reset", None, None),
        (1, "customize", "Riassumi.", "s1"),
    ]
    read = await contract_store.customizations("test.job")
    assert read.prompts == {"summary": reset}
    assert await contract_store.prompt_history("test.job", "other") == []
