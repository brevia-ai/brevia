"""Jobs on PostgreSQL with real worker processes, stopped by the tests.

Each test uses its own Brevia and jobs schemas. Workers are ``brevia worker``
processes running ``job_app``; a worker asked to crash kills itself with SIGKILL.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from brevia import (
    Brevia,
    InternalError,
    RunTimeout,
    Unavailable,
)
from brevia.db import migrate
from brevia.db.engine import sync_engine
from brevia.db.jobs import NewJob
from brevia.db.runs import RunOutcome
from brevia.files.retention import clean
from brevia.jobs.backend import DbosBackend
from brevia.models.limits import CallUsage
from integration.job_app import PROJECT, Answers, build

pytestmark = pytest.mark.integration

TESTS = Path(__file__).parents[1]
WAIT = 60


@pytest.fixture
def environment(
    database_url: str,
    schema: str,
    jobs_schema: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    migrate.upgrade(database_url, schema)
    migrate.upgrade_jobs(database_url, jobs_schema)
    values = {
        "BREVIA_DATABASE_URL": database_url,
        "BREVIA_DATABASE_SCHEMA": schema,
        "BREVIA_JOBS_SCHEMA": jobs_schema,
        "BREVIA_PROJECT_FILE": str(tmp_path / "brevia.toml"),
        "BREVIA_WORKER_SHUTDOWN_SECONDS": "5",
        "JOB_CALL_LOG": str(tmp_path / "calls.log"),
        "JOB_CRASH_MARKER": str(tmp_path / "crashed"),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


@pytest.fixture
async def app(environment: dict[str, str]) -> AsyncIterator[Brevia]:
    """The application in the test process: it submits and reads jobs."""
    async with build() as brevia:
        yield brevia


class Worker:
    """A ``brevia worker`` process."""

    def __init__(self, environment: dict[str, str], log: Path) -> None:
        self._environment = environment
        self._log = log
        self.process: subprocess.Popen[bytes] | None = None

    def start(
        self,
        version: str = "A",
        worker_id: str = "w1",
        crash_at: str | None = None,
        **extra: str,
    ) -> None:
        env = {
            **os.environ,
            **self._environment,
            "BREVIA_APP_VERSION": version,
            "BREVIA_WORKER_ID": worker_id,
            "JOB_CRASH_AT": crash_at or "",
            **extra,
        }
        self._log.write_text("", encoding="utf-8")
        with self._log.open("ab") as log:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "brevia.cli",
                    "worker",
                    "integration.job_app:build",
                ],
                cwd=TESTS,
                env=env,
                stdout=log,
                stderr=log,
            )
        deadline = time.monotonic() + WAIT
        while "Job worker w" not in self._log.read_text(encoding="utf-8"):
            if self.process.poll() is not None or time.monotonic() > deadline:
                raise AssertionError(f"worker did not start:\n{self.output()}")
            time.sleep(0.1)

    def output(self) -> str:
        return self._log.read_text(encoding="utf-8")

    async def crashed(self) -> None:
        """Wait for the worker to kill itself."""
        assert self.process is not None
        for _ in range(WAIT * 10):
            if self.process.poll() is not None:
                assert self.process.returncode == -signal.SIGKILL, self.output()
                return
            await asyncio.sleep(0.1)
        raise AssertionError("worker did not crash")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


@pytest.fixture
def worker(environment: dict[str, str], tmp_path: Path) -> Iterator[Worker]:
    started = Worker(environment, tmp_path / "worker.log")
    yield started
    started.stop()


def _calls(environment: dict[str, str]) -> list[str]:
    path = Path(environment["JOB_CALL_LOG"])
    if not path.exists():
        return []
    return [line.split(" ", 1)[1] for line in path.read_text().splitlines()]


def _rows(url: str, schema: str, query: str, **values: Any) -> list[Any]:
    engine = sync_engine(url)
    try:
        with engine.connect() as connection:
            return list(
                connection.execute(text(query.replace("{schema}", schema)), values)
            )
    finally:
        engine.dispose()


def _write(environment: dict[str, str], query: str, **values: Any) -> None:
    """Run a statement on the Brevia schema of the test."""
    engine = sync_engine(environment["BREVIA_DATABASE_URL"])
    statement = text(query.replace("{schema}", environment["BREVIA_DATABASE_SCHEMA"]))
    try:
        with engine.begin() as connection:
            connection.execute(statement, values)
    finally:
        engine.dispose()


async def _running(app: Brevia, run_id: str) -> None:
    for _ in range(WAIT * 10):
        if (await app.job(run_id).status()).status != "queued":
            return
        await asyncio.sleep(0.1)
    raise AssertionError("the job did not start")


# ---------- submission ----------


async def test_a_job_is_recorded_and_queued_together_or_not_at_all(
    app: Brevia,
) -> None:
    backend = app._jobs_backend
    assert isinstance(backend, DbosBackend)
    run_id = uuid.uuid4()
    job = NewJob(
        id=run_id,
        activity="test.two_calls",
        activity_version="1",
        input={"text": "q"},
        overrides={},
        idempotency_key=None,
        fingerprint="f",
        retry_of_run_id=None,
        created_at=datetime.now(UTC),
    )

    def enqueue_then_fail(connection: Any) -> None:
        backend.enqueue(connection, str(run_id))
        raise RuntimeError("stop after queueing")

    with pytest.raises(Unavailable) as caught:
        await app._store.submit_job(job, enqueue_then_fail)
    assert caught.value.details == {"cause": ["RuntimeError"]}
    assert await app._store.job(run_id) is None
    assert await backend.status(str(run_id)) is None


async def test_concurrent_submissions_with_one_key_give_one_job(
    app: Brevia, environment: dict[str, str]
) -> None:
    handles = await asyncio.gather(
        *(
            app.submit("test.two_calls", {"text": "q"}, idempotency_key="same")
            for _ in range(5)
        )
    )
    assert len({h.run_id for h in handles}) == 1
    rows = _rows(
        environment["BREVIA_DATABASE_URL"],
        environment["BREVIA_DATABASE_SCHEMA"],
        "SELECT count(*) FROM {schema}.runs",
    )
    assert rows[0][0] == 1
    queued = _rows(
        environment["BREVIA_DATABASE_URL"],
        environment["BREVIA_JOBS_SCHEMA"],
        "SELECT count(*) FROM {schema}.workflow_status",
    )
    assert queued[0][0] == 1


async def test_a_queued_job_is_cancelled_in_both_records(app: Brevia) -> None:
    handle = await app.submit("test.two_calls", {"text": "q"})
    assert (await handle.cancel()).status == "cancelled"
    backend = app._jobs_backend
    assert backend is not None
    assert await backend.status(handle.run_id) == "CANCELLED"


# ---------- execution and resumption ----------


async def test_a_worker_runs_a_job_and_records_its_calls(
    app: Brevia, worker: Worker, environment: dict[str, str]
) -> None:
    worker.start()
    handle = await app.submit("test.two_calls", {"text": "q"})
    result = await handle.result(wait=WAIT)
    assert result == Answers(
        first="answer to first q", second="answer to second q", language="it"
    )
    state = await handle.status()
    assert state.usage is not None
    assert state.usage["requests"] == 2
    assert state.usage["cost_kind"] == "estimate"
    url, schema = (
        environment["BREVIA_DATABASE_URL"],
        environment["BREVIA_DATABASE_SCHEMA"],
    )
    calls = _rows(
        url,
        schema,
        "SELECT sequence, error FROM {schema}.model_calls "
        "WHERE run_id = :id ORDER BY sequence",
        id=handle.run_id,
    )
    assert [tuple(c) for c in calls] == [(0, None), (1, None)]
    contents = _rows(url, schema, "SELECT count(*) FROM {schema}.trace_contents")
    assert contents[0][0] == 2


async def test_an_interrupted_job_starts_again_from_the_beginning(
    app: Brevia, worker: Worker, environment: dict[str, str]
) -> None:
    worker.start(crash_at="between-calls")
    handle = await app.submit("test.two_calls", {"text": "q"})
    await worker.crashed()
    assert (await handle.status()).status == "running"
    # A customisation made meanwhile does not apply to the job already started.
    await app.customize_configuration("test.two_calls", {"language": "en"})
    worker.start()
    result = await handle.result(wait=WAIT)
    assert result.model_dump()["language"] == "it"
    # The first call is made again; only the calls of the last execution are recorded.
    assert _calls(environment) == ["first q", "first q", "second q"]
    calls = _rows(
        environment["BREVIA_DATABASE_URL"],
        environment["BREVIA_DATABASE_SCHEMA"],
        "SELECT sequence FROM {schema}.model_calls WHERE run_id = :id "
        "ORDER BY sequence",
        id=handle.run_id,
    )
    assert [tuple(c) for c in calls] == [(0,), (1,)]
    usage = (await handle.status()).usage
    assert usage is not None
    assert usage["requests"] == 2


async def test_the_calls_of_an_execution_lost_with_its_worker_are_not_recorded(
    app: Brevia, worker: Worker, environment: dict[str, str]
) -> None:
    worker.start(crash_at="in-second-call")
    handle = await app.submit("test.two_calls", {"text": "q"})
    await worker.crashed()
    worker.start()
    await handle.result(wait=WAIT)
    # Both calls ran again: the lost execution paid for its calls too.
    assert _calls(environment) == ["first q", "second q", "first q", "second q"]
    calls = _rows(
        environment["BREVIA_DATABASE_URL"],
        environment["BREVIA_DATABASE_SCHEMA"],
        "SELECT sequence, cost_usd IS NULL FROM {schema}.model_calls "
        "WHERE run_id = :id ORDER BY sequence",
        id=handle.run_id,
    )
    assert [tuple(c) for c in calls] == [(0, False), (1, False)]
    usage = (await handle.status()).usage
    assert usage is not None
    assert usage["requests"] == 2
    assert usage["cost_kind"] == "estimate"


async def test_a_release_fails_interrupted_jobs_and_runs_queued_ones(
    app: Brevia, worker: Worker
) -> None:
    worker.start(version="A", crash_at="between-calls")
    interrupted = await app.submit("test.two_calls", {"text": "interrupted"})
    await worker.crashed()
    queued = await app.submit("test.two_calls", {"text": "queued"})
    worker.start(version="B")
    assert (await queued.result(wait=WAIT)).model_dump()["second"] == (
        "answer to second queued"
    )
    with pytest.raises(InternalError) as caught:
        await interrupted.result(wait=WAIT)
    assert caught.value.retryable
    assert caught.value.details == {"app_version": "A"}
    retried = await interrupted.retry()
    assert (await retried.result(wait=WAIT)).model_dump()["first"] == (
        "answer to first interrupted"
    )


async def test_a_stopped_worker_lets_running_jobs_end(
    app: Brevia, worker: Worker
) -> None:
    worker.start()
    handle = await app.submit("test.two_calls", {"text": "q"})
    await _running(app, handle.run_id)
    worker.stop()
    assert worker.process is not None
    assert worker.process.returncode == 0, worker.output()
    state = await handle.status()
    assert state.status in ("running", "succeeded")
    if state.status == "running":  # interrupted by the stop: started again
        worker.start()
    await handle.result(wait=WAIT)


async def test_a_job_still_running_at_shutdown_starts_again_on_restart(
    app: Brevia, worker: Worker, environment: dict[str, str]
) -> None:
    worker.start(JOB_HOLD_SECONDS="60", BREVIA_WORKER_SHUTDOWN_SECONDS="1")
    handle = await app.submit("test.two_calls", {"text": "q"})
    for _ in range(WAIT * 10):
        if _calls(environment):
            break
        await asyncio.sleep(0.1)
    worker.stop()
    assert worker.process is not None
    assert worker.process.returncode == 0, worker.output()
    assert (await handle.status()).status == "running"
    worker.start()
    result = await handle.result(wait=WAIT)
    assert result.model_dump()["second"] == "answer to second q"
    assert _calls(environment) == ["first q", "first q", "second q"]
    usage = (await handle.status()).usage
    assert usage is not None
    assert usage["requests"] == 2


def _outcome(run_id: str, status: Any) -> RunOutcome:
    call = CallUsage(
        model="openai:test-model",
        options={},
        started_at=datetime.now(UTC),
        requests=1,
        tool_calls=0,
        input_tokens=10,
        output_tokens=2,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=Decimal("0.5"),
        prices=None,
        seconds=0.1,
    )
    return RunOutcome(
        id=uuid.UUID(run_id),
        status=status,
        result={} if status == "succeeded" else None,
        error=None,
        usage={"requests": 1},
        calls=[call],
        adapter={"name": "pydantic-ai", "version": "x"},
        finished_at=datetime.now(UTC),
    )


async def test_the_outcome_of_a_job_is_written_once(
    app: Brevia, environment: dict[str, str]
) -> None:
    url, schema = (
        environment["BREVIA_DATABASE_URL"],
        environment["BREVIA_DATABASE_SCHEMA"],
    )

    def calls(run_id: str) -> int:
        query = "SELECT count(*) FROM {schema}.model_calls WHERE run_id = :id"
        return int(_rows(url, schema, query, id=run_id)[0][0])

    ended = await app.submit("test.two_calls", {"text": "ended"})
    # Written again by an execution that stopped before the engine recorded the end.
    await app._store.finish_run(_outcome(ended.run_id, "succeeded"))
    await app._store.finish_run(_outcome(ended.run_id, "succeeded"))
    assert calls(ended.run_id) == 1
    assert (await ended.status()).status == "succeeded"

    stopped = await app.submit("test.two_calls", {"text": "stopped"})
    # A stop of the worker cancels the run, not the job: nothing is written.
    await app._store.finish_run(_outcome(stopped.run_id, "cancelled"))
    assert calls(stopped.run_id) == 0
    assert (await stopped.status()).status == "queued"

    # A job cancelled meanwhile receives the usage and the calls of its run, once.
    await stopped.cancel()
    await app._store.finish_run(_outcome(stopped.run_id, "cancelled"))
    await app._store.finish_run(_outcome(stopped.run_id, "cancelled"))
    assert calls(stopped.run_id) == 1
    state = await stopped.status()
    assert state.status == "cancelled"
    assert state.usage == {"requests": 1}


async def test_a_job_started_again_after_its_deadline_records_a_timeout(
    app: Brevia, worker: Worker, environment: dict[str, str]
) -> None:
    worker.start(crash_at="between-calls", JOB_MAX_SECONDS="3")
    handle = await app.submit("test.two_calls", {"text": "q"})
    await worker.crashed()
    await asyncio.sleep(3.5)  # the deadline passes while no worker runs the job
    worker.start()
    with pytest.raises(RunTimeout):
        await handle.result(wait=WAIT)
    state = await handle.status()
    assert state.error is not None
    assert state.error["code"] == "timeout"
    assert _calls(environment) == ["first q"]


# ---------- cleanup of expired data ----------


def _contents(environment: dict[str, str], run_id: str) -> list[Any]:
    return _rows(
        environment["BREVIA_DATABASE_URL"],
        environment["BREVIA_DATABASE_SCHEMA"],
        "SELECT mc.sequence, tc.instructions IS NULL, tc.call_id, tc.deleted_at, "
        "tc.expires_at, r.finished_at FROM {schema}.trace_contents tc "
        "JOIN {schema}.model_calls mc ON mc.id = tc.call_id "
        "JOIN {schema}.runs r ON r.id = mc.run_id WHERE r.id = :id "
        "ORDER BY mc.sequence",
        id=run_id,
    )


async def test_cleanup_clears_expired_contents_and_steps_of_ended_jobs(
    app: Brevia, worker: Worker, environment: dict[str, str]
) -> None:
    worker.start()
    ended = await app.submit("test.two_calls", {"text": "q"})
    await ended.result(wait=WAIT)
    worker.stop()
    first, second = _contents(environment, ended.run_id)
    # Contents expire retention_days (30) after the end of the job.
    assert first[4] - first[5] == timedelta(days=30)
    _write(
        environment,
        "UPDATE {schema}.trace_contents SET expires_at = now() - interval '1 second' "
        "WHERE call_id = :id",
        id=first[2],
    )
    worker.start(crash_at="between-calls")
    running = await app.submit("test.two_calls", {"text": "r"})
    await worker.crashed()
    backend = app._jobs_backend
    assert backend is not None
    store, retention = app._store, app.project.traces.retention_days

    counted = await clean(store, backend, retention, dry_run=True)
    assert (counted.contents, counted.job_steps) == (1, 0)
    cleared = await clean(store, backend, retention)
    assert (cleared.contents, cleared.job_steps) == (1, 0)
    first, second = _contents(environment, ended.run_id)
    assert first[1] is True  # cleared
    assert first[3] is not None
    assert second[1] is False
    assert second[3] is None

    # Past the retention, the steps of the ended job go; the started one stays.
    later = datetime.now(UTC) + timedelta(days=31)
    cleared = await clean(store, backend, retention, now=later)
    assert cleared.job_steps == 1
    assert await backend.status(ended.run_id) is None
    assert await backend.status(running.run_id) == "PENDING"
    assert (await ended.status()).status == "succeeded"  # the record stays


def test_the_cleanup_command_counts_and_deletes(
    environment: dict[str, str], tmp_path: Path
) -> None:
    Path(environment["BREVIA_PROJECT_FILE"]).write_text(PROJECT, encoding="utf-8")

    def brevia(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603  (fixed arguments)
            [sys.executable, "-m", "brevia.cli", "db", "cleanup", *args],
            env={**os.environ, **environment},
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

    dry = brevia("--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert "would be deleted: 0" in dry.stdout
    done = brevia()
    assert done.returncode == 0, done.stderr
    assert "deleted: 0" in done.stdout
    assert "retention 30 days" in done.stdout


async def test_workers_keep_one_daily_cleanup_that_runs(
    app: Brevia, worker: Worker, environment: dict[str, str], tmp_path: Path
) -> None:
    worker.start()
    other = Worker(environment, tmp_path / "other.log")
    try:
        other.start(worker_id="w2")
        backend = app._jobs_backend
        assert isinstance(backend, DbosBackend)
        schedules = await asyncio.to_thread(backend.client.list_schedules)
        assert [s["schedule_name"] for s in schedules] == ["brevia.cleanup"]
        assert schedules[0]["schedule"] == "0 3 * * *"
        handle = await asyncio.to_thread(
            backend.client.trigger_schedule, "brevia.cleanup"
        )
        for _ in range(WAIT * 10):
            status = await backend.status(handle.get_workflow_id())
            if status == "SUCCESS":
                break
            await asyncio.sleep(0.1)
        assert status == "SUCCESS"
    finally:
        other.stop()
