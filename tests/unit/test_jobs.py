"""Jobs: submission, durable execution, status, cancellation and retry.

DBOS runs in this process on SQLite, with the store in memory: the same workflow and
steps as a worker, without services. Interruptions of real worker processes are
covered by the integration tests on PostgreSQL.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx2
import pytest
from conftest import answers, project_brevia, simulated
from dbos import DBOS
from memory_store import MemoryStore
from pydantic import BaseModel, Field, computed_field, field_serializer
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from summary_example import NoConfig, SummaryConfig, SummaryRequest, SummaryResult

from brevia import (
    AccessPolicy,
    Brevia,
    BreviaSettings,
    Busy,
    Caller,
    Cancelled,
    FileRef,
    FileSource,
    FileStore,
    IdempotencyConflict,
    InternalError,
    InvalidInput,
    NotFound,
    NotReady,
    OutputInvalid,
    OverrideNotAllowed,
    RunContext,
    RunTimeout,
    Unsupported,
    __version__,
)
from brevia.cli import main
from brevia.files.retention import clean
from brevia.jobs import workflow
from brevia.jobs.backend import QUEUE, DbosBackend, guard_engine_logs
from brevia.jobs.worker import _stop_running_jobs, engine_version, launch

pytestmark = pytest.mark.unit

VERSION = "test-1"
WAIT = 10


class Gate:
    """Lets a test hold an activity until it says so."""

    entered: asyncio.Event
    release: asyncio.Event
    left: asyncio.Event

    def reset(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.left = asyncio.Event()


GATE = Gate()


async def held_summary(
    request: SummaryRequest, ctx: RunContext[SummaryConfig]
) -> SummaryResult:
    """Waits at the gate, then summarises in the configured language."""
    GATE.entered.set()
    try:
        await GATE.release.wait()
        result: SummaryResult = await ctx.model().generate(
            instructions=f"Summarise in {ctx.config.language}.",
            user_text=request.text,
            output_type=SummaryResult,
        )
    finally:
        GATE.left.set()
    return SummaryResult(summary=f"{ctx.config.language}: {result.summary}")


async def no_model(request: SummaryRequest, ctx: RunContext[NoConfig]) -> SummaryResult:
    return SummaryResult(summary=request.text)


SECRET = "".join(["confidential ", "host"])  # not in the source of the tests


async def chained(request: SummaryRequest, ctx: RunContext[NoConfig]) -> SummaryResult:
    """Fails with a Brevia error raised while handling an error of a dependency."""
    try:
        raise RuntimeError(SECRET)
    except RuntimeError as exc:
        raise InvalidInput("The document cannot be read") from exc


class CopyRequest(BaseModel):
    document: FileSource


class CopyResult(BaseModel):
    output: FileRef


async def copy_document(request: CopyRequest, ctx: RunContext[NoConfig]) -> CopyResult:
    path = await ctx.files.local_path(request.document)
    return CopyResult(output=await ctx.files.save("copy.pdf", path.read_bytes()))


class LabelRequest(BaseModel):
    label_text: str = Field(alias="labelText")


class LabelResult(BaseModel):
    label_text: str = Field(alias="labelText")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def length(self) -> int:
        return len(self.label_text)


async def label(request: LabelRequest, ctx: RunContext[NoConfig]) -> LabelResult:
    return LabelResult(labelText=request.label_text.upper())


class Hidden(BaseModel):
    code: int

    @field_serializer("code")
    def _code(self, code: int) -> str:
        return f"#{code}"  # a JSON form that the schema does not read back


async def hidden(request: LabelRequest, ctx: RunContext[NoConfig]) -> Hidden:
    return Hidden(code=7)


class Renamed(BaseModel):
    # Written as "outName" but read only as "inName": a record it cannot read back.
    text: str = Field(validation_alias="inName", serialization_alias="outName")


async def renamed(request: Renamed, ctx: RunContext[NoConfig]) -> Hidden:
    return Hidden(code=1)


FILES_HOST = "files.example.org"

Launcher = Callable[[], Awaitable[None]]


@pytest.fixture
async def unlaunched(
    tmp_path: Path, store: MemoryStore
) -> AsyncIterator[tuple[Brevia, Launcher]]:
    """A started Brevia with jobs, and the function that launches its worker."""
    GATE.reset()
    url = f"sqlite:///{tmp_path / 'jobs.sqlite'}"
    DBOS.migrate(url)
    backend = DbosBackend(url, "dbos")
    files = FileStore(tmp_path / "files", allowed_hosts=frozenset({FILES_HOST}))
    app = project_brevia(
        tmp_path, store, modes=("direct", "job"), jobs=backend, files=files
    )
    app.register_activity(
        name="test.copy",
        version="1",
        function=copy_document,
        input_type=CopyRequest,
        output_type=CopyResult,
        config_type=NoConfig,
        modes=("job",),
    )
    app.register_activity(
        name="test.label",
        version="1",
        function=label,
        input_type=LabelRequest,
        output_type=LabelResult,
        config_type=NoConfig,
        modes=("direct", "job"),
    )
    app.register_activity(
        name="test.renamed",
        version="1",
        function=renamed,
        input_type=Renamed,
        output_type=Hidden,
        config_type=NoConfig,
        modes=("job",),
    )
    app.register_activity(
        name="test.hidden",
        version="1",
        function=hidden,
        input_type=LabelRequest,
        output_type=Hidden,
        config_type=NoConfig,
        modes=("direct", "job"),
    )
    for name, function, config in (
        ("test.held", held_summary, SummaryConfig),
        ("test.no-model", no_model, NoConfig),
        ("test.chained", chained, NoConfig),
    ):
        app.register_activity(
            name=name,
            version="1",
            function=function,
            input_type=SummaryRequest,
            output_type=SummaryResult,
            config_type=config,
            customizable=["language"] if config is SummaryConfig else (),
            modes=("job",),
            capture="full" if name == "test.held" else "metadata",
        )
    await app.start()

    async def launched() -> None:
        launch(app, backend, VERSION, "unit-worker")
        await DBOS.register_queue_async(QUEUE, polling_interval_sec=0.05)

    try:
        yield app, launched
    finally:
        GATE.release.set()
        await asyncio.to_thread(DBOS.destroy, workflow_completion_timeout_sec=0)
        workflow.install(None)
        await app.stop()


@pytest.fixture
async def jobs(unlaunched: tuple[Brevia, Launcher]) -> Brevia:
    app, launched = unlaunched
    await launched()
    return app


async def _until(condition: Callable[[], bool]) -> None:
    for _ in range(WAIT * 20):
        if condition():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition not reached")


async def _stop_worker() -> None:
    """Stop the worker of the test as a worker process that stops during a job."""
    await asyncio.to_thread(DBOS.destroy, workflow_completion_timeout_sec=0)
    await _stop_running_jobs()


async def _status_becomes(app: Brevia, run_id: str, status: str) -> None:
    for _ in range(WAIT * 20):
        if (await app.job(run_id).status()).status == status:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"job did not become {status}")


# ---------- submission and outcome ----------


async def test_a_job_runs_and_records_its_outcome_and_calls(
    jobs: Brevia, store: MemoryStore
) -> None:
    with simulated(answers({"summary": "Breve."})):
        handle = await jobs.submit("document.summarize", {"text": "Un testo."})
        result = await handle.result(wait=WAIT)

    assert result == SummaryResult(summary="Breve.")
    state = await handle.status()
    assert state.status == "succeeded"
    assert state.done
    assert state.error is None
    assert state.retry_of is None
    assert state.started_at is not None
    assert state.finished_at is not None
    assert state.usage == {
        "requests": 1,
        "tool_calls": 0,
        "input_tokens": 100,
        "output_tokens": 10,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cost_usd": "0.00012",
        "cost_kind": "estimate",
    }
    record = store.jobs[uuid.UUID(handle.run_id)]
    assert record.snapshot is not None
    assert record.snapshot["config"]["language"] == "it"
    # The version the worker runs the job under.
    assert record.snapshot["application"] == {"version": VERSION}
    assert record.deadline_at is not None
    (call,) = store.calls_of(record.id)
    assert call.error is None
    assert call.cost_usd == Decimal("0.00012")


async def test_schemas_with_aliases_and_computed_fields_work_in_jobs(
    jobs: Brevia, store: MemoryStore
) -> None:
    handle = await jobs.submit("test.label", {"labelText": "ab"})
    result = await handle.result(wait=WAIT)

    assert result == LabelResult(labelText="AB")
    record = store.jobs[uuid.UUID(handle.run_id)]
    # Recorded under the aliases, without the computed field.
    assert record.input == {"labelText": "ab"}
    assert record.result == {"labelText": "AB"}
    assert await jobs.run("test.label", LabelRequest(labelText="c")) == LabelResult(
        labelText="C"
    )


async def test_an_output_its_schema_cannot_read_back_fails_the_job(
    jobs: Brevia,
) -> None:
    handle = await jobs.submit("test.hidden", {"labelText": "a"})
    with pytest.raises(InternalError, match="read back"):
        await handle.result(wait=WAIT)
    assert (await handle.status()).status == "failed"
    # A direct run returns the output itself, without reading the record.
    assert await jobs.run("test.hidden", {"labelText": "a"}) == Hidden(code=7)


async def test_an_input_its_schema_cannot_read_back_is_refused_as_internal(
    jobs: Brevia, store: MemoryStore
) -> None:
    with pytest.raises(InternalError, match="read back"):
        await jobs.submit("test.renamed", {"inName": "a"})
    assert store.jobs == {}


async def test_a_job_without_model_calls_has_zero_usage(jobs: Brevia) -> None:
    handle = await jobs.submit("test.no-model", {"text": "eco"})
    assert await handle.result(wait=WAIT) == SummaryResult(summary="eco")
    usage = (await handle.status()).usage
    assert usage is not None
    assert usage["requests"] == 0
    assert usage["cost_usd"] == "0"


async def test_the_contents_of_calls_are_recorded_when_captured(
    jobs: Brevia, store: MemoryStore
) -> None:
    GATE.release.set()
    with simulated(answers({"summary": "Breve."})):
        handle = await jobs.submit("test.held", {"text": "Testo da tenere."})
        await handle.result(wait=WAIT)
    (call,) = store.calls_of(uuid.UUID(handle.run_id))
    assert call.content is not None
    assert call.content.user_text == "Testo da tenere."
    assert call.content.output == {"summary": "Breve."}


async def test_a_failed_job_reports_its_error(jobs: Brevia) -> None:
    invalid = {"wrong": "field"}
    with simulated(answers(invalid, invalid, invalid)):
        handle = await jobs.submit("document.summarize", {"text": "Un testo."})
        with pytest.raises(OutputInvalid) as caught:
            await handle.result(wait=WAIT)
    state = await handle.status()
    assert state.status == "failed"
    assert state.error is not None
    assert state.error["code"] == "output_invalid"
    assert caught.value.details == state.error["details"]
    assert state.usage is not None
    assert state.usage["requests"] == 3


async def test_the_engine_logs_no_chain_of_a_failed_job(
    jobs: Brevia, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    handle = await jobs.submit("test.chained", {"text": "x"})
    with pytest.raises(InvalidInput) as caught:
        await handle.result(wait=WAIT)
    assert caught.value.message == "The document cannot be read"
    # The failure, logged through the handlers of the application, by type only. The
    # engine logs it after the job is recorded as failed: wait for the record.
    expected = "Exception encountered in asynchronous workflow: (InvalidInput)"
    await _until(
        lambda: expected in [r.getMessage() for r in caplog.records if r.name == "dbos"]
    )
    assert SECRET not in caplog.text
    engine = [r for r in caplog.records if r.name == "dbos"]
    assert all(r.exc_info is None for r in engine)


def test_records_of_the_engine_keep_no_details() -> None:
    guard_engine_logs()
    engine = logging.getLogger("dbos")
    records: list[logging.LogRecord] = []

    class Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    keep = Keep()
    engine.addHandler(keep)
    try:
        engine.error(f"Error connecting to the DBOS system database: {SECRET}")
        try:
            raise RuntimeError(SECRET)
        except RuntimeError as exc:
            engine.warning("Step being automatically retried", exc_info=exc)
        engine.debug(SECRET)
        engine.info(f"Initializing DBOS with URL: {SECRET}")
    finally:
        engine.removeHandler(keep)
    assert [r.getMessage() for r in records] == [
        "Error connecting to the DBOS system database",
        "Step being automatically retried (RuntimeError)",
        "Initializing DBOS with URL",
    ]
    assert all(r.exc_info is None for r in records)


async def test_the_result_is_not_ready_while_the_job_runs(jobs: Brevia) -> None:
    handle = await jobs.submit("test.held", {"text": "Un testo."})
    await asyncio.wait_for(GATE.entered.wait(), WAIT)
    with pytest.raises(NotReady) as caught:
        await handle.result()
    assert caught.value.details["status"] == "running"
    with pytest.raises(NotReady):
        await handle.result(wait=0.2)
    with simulated(answers({"summary": "Breve."})):
        GATE.release.set()
        assert await handle.result(wait=WAIT) == SummaryResult(summary="it: Breve.")


# ---------- checks at submission ----------


async def test_the_same_key_and_request_return_the_same_job(
    jobs: Brevia, store: MemoryStore
) -> None:
    with simulated(answers({"summary": "Breve."})):
        first = await jobs.submit(
            "document.summarize", {"text": "Un testo."}, idempotency_key="k-1"
        )
        await first.result(wait=WAIT)
        again = await jobs.submit(
            "document.summarize", {"text": "Un testo."}, idempotency_key="k-1"
        )
    assert again.run_id == first.run_id
    assert len(store.jobs) == 1
    assert (await again.status()).status == "succeeded"


async def test_a_repeated_submission_does_not_depend_on_the_configuration(
    unlaunched: tuple[Brevia, Launcher], store: MemoryStore
) -> None:
    app, _ = unlaunched
    first = await app.submit("document.summarize", {"text": "A"}, idempotency_key="k")
    # The configuration can no longer be resolved: a new job would be refused, the
    # job accepted earlier is still returned to a caller that lost the response.
    store.fail.add("customizations")
    again = await app.submit("document.summarize", {"text": "A"}, idempotency_key="k")
    assert again.run_id == first.run_id
    with pytest.raises(IdempotencyConflict):
        await app.submit("document.summarize", {"text": "B"}, idempotency_key="k")


async def test_the_same_key_with_another_request_is_a_conflict(
    unlaunched: tuple[Brevia, Launcher], store: MemoryStore
) -> None:
    app, _ = unlaunched
    first = await app.submit("document.summarize", {"text": "A"}, idempotency_key="k")
    with pytest.raises(IdempotencyConflict) as caught:
        await app.submit("document.summarize", {"text": "B"}, idempotency_key="k")
    assert caught.value.details == {"run_id": first.run_id}
    with pytest.raises(IdempotencyConflict):
        await app.submit(
            "document.summarize",
            {"text": "A"},
            {"language": "en"},
            idempotency_key="k",
        )
    assert len(store.jobs) == 1


async def test_keys_are_scoped_to_the_activity(
    unlaunched: tuple[Brevia, Launcher],
) -> None:
    app, _ = unlaunched
    first = await app.submit("document.summarize", {"text": "A"}, idempotency_key="k")
    other = await app.submit("test.no-model", {"text": "A"}, idempotency_key="k")
    assert first.run_id != other.run_id


async def test_keys_are_scoped_to_the_caller(
    unlaunched: tuple[Brevia, Launcher], store: MemoryStore
) -> None:
    app, _ = unlaunched
    one, two = Caller("backend-one", end_user="user-7"), Caller("backend-two")
    first = await app.submit(
        "document.summarize", {"text": "A"}, idempotency_key="k", caller=one
    )
    # Another caller with the same key and another request gets a job of its own,
    # not a conflict that would name the job of the first caller.
    other = await app.submit(
        "document.summarize", {"text": "B"}, idempotency_key="k", caller=two
    )
    local = await app.submit("document.summarize", {"text": "C"}, idempotency_key="k")
    assert len({first.run_id, other.run_id, local.run_id}) == 3
    record = store.jobs[uuid.UUID(first.run_id)]
    assert (record.caller, record.end_user) == ("backend-one", "user-7")
    assert store.jobs[uuid.UUID(local.run_id)].caller is None
    again = await app.submit(
        "document.summarize", {"text": "A"}, idempotency_key="k", caller=one
    )
    assert again.run_id == first.run_id
    with pytest.raises(IdempotencyConflict) as caught:
        await app.submit(
            "document.summarize", {"text": "Z"}, idempotency_key="k", caller=one
        )
    assert caught.value.details == {"run_id": first.run_id}  # a job of its own


async def test_a_caller_does_not_find_the_jobs_of_another(
    unlaunched: tuple[Brevia, Launcher],
) -> None:
    app, _ = unlaunched
    owner, other = Caller("owner"), Caller("other")
    handle = await app.submit("document.summarize", {"text": "A"}, caller=owner)
    assert handle.caller == owner
    missing = app.job(str(uuid.uuid4()), caller=other)
    for job in (app.job(handle.run_id, caller=other), missing):
        for operation in (job.status, job.result, job.cancel, job.retry):
            with pytest.raises(NotFound) as caught:
                await operation()
            # The same error as for a job that does not exist: nothing is revealed.
            assert caught.value.details == {"run_id": job.run_id}
    assert (await app.job(handle.run_id, caller=owner).status()).status == "queued"
    assert (await app.job(handle.run_id).status()).status == "queued"  # trusted code
    # A job of trusted code is not visible to a caller either.
    local = await app.submit("document.summarize", {"text": "B"})
    with pytest.raises(NotFound):
        await app.job(local.run_id, caller=owner).status()


async def test_administrators_and_the_shared_policy_see_every_job(
    tmp_path: Path, store: MemoryStore
) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.sqlite'}"
    DBOS.migrate(url)
    owner, admin = Caller("owner", end_user="user-7"), Caller("admin")
    for policy, reader in (
        (AccessPolicy(admins=frozenset({"admin"})), admin),
        (AccessPolicy(shared=True), Caller("anyone")),
    ):
        app = project_brevia(
            tmp_path,
            store,
            modes=("job",),
            jobs=DbosBackend(url, "dbos"),
            access=policy,
        )
        async with app:
            handle = await app.submit("document.summarize", {"text": "A"}, caller=owner)
            job = app.job(handle.run_id, caller=reader)
            assert (await job.cancel()).status == "cancelled"
            retried = await job.retry()
            assert retried.caller == reader
            record = store.jobs[uuid.UUID(retried.run_id)]
            # The retried job still belongs to the caller of the cancelled one.
            assert (record.caller, record.end_user) == ("owner", "user-7")
            await retried.cancel()


async def test_the_outputs_of_a_job_are_read_by_its_caller(
    jobs: Brevia, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"%PDF-1.7 synthetic"
    transport = httpx2.MockTransport(
        lambda request: httpx2.Response(200, content=content)
    )
    monkeypatch.setattr("brevia.files.files._transport", transport)
    owner = Caller("owner")
    document = {"name": "in.pdf", "url": f"https://{FILES_HOST}/in.pdf"}
    handle = await jobs.submit("test.copy", {"document": document}, caller=owner)
    result = await handle.result(wait=WAIT)
    assert isinstance(result, CopyResult)
    path = await handle.file("copy.pdf")
    assert path.read_bytes() == content
    assert result.output.sha256 == hashlib.sha256(content).hexdigest()
    for job, name in (
        (jobs.job(handle.run_id, caller=Caller("other")), "copy.pdf"),
        (handle, "missing.pdf"),
        (handle, "../copy.pdf"),
    ):
        with pytest.raises(NotFound):
            await job.file(name)
    assert not (jobs.files.root / "work" / handle.run_id).exists()  # type: ignore[union-attr]


async def test_a_repeated_submission_finds_its_job_after_the_file_settings_change(
    unlaunched: tuple[Brevia, Launcher], store: MemoryStore, tmp_path: Path
) -> None:
    app, _ = unlaunched
    document = {"name": "in.pdf", "url": f"https://{FILES_HOST}/in.pdf"}
    first = await app.submit("test.copy", {"document": document}, idempotency_key="k")
    # The host is no longer allowed: a new job is refused, the accepted one is found.
    stricter = FileStore(tmp_path / "files")
    url = f"sqlite:///{tmp_path / 'jobs.sqlite'}"
    later = project_brevia(
        tmp_path, store, modes=("job",), jobs=DbosBackend(url, "dbos"), files=stricter
    )
    later.register_activity(
        name="test.copy",
        version="1",
        function=copy_document,
        input_type=CopyRequest,
        output_type=CopyResult,
        config_type=NoConfig,
        modes=("job",),
    )
    async with later:
        again = await later.submit(
            "test.copy", {"document": document}, idempotency_key="k"
        )
        assert again.run_id == first.run_id
        with pytest.raises(InvalidInput):
            await later.submit(
                "test.copy", {"document": document}, idempotency_key="other"
            )


@pytest.mark.parametrize("key", ["", "   ", "x" * 201, "a\x00b"])
async def test_blank_long_or_nul_keys_are_refused(
    unlaunched: tuple[Brevia, Launcher], key: str
) -> None:
    app, _ = unlaunched
    with pytest.raises(InvalidInput):
        await app.submit("document.summarize", {"text": "A"}, idempotency_key=key)
    with pytest.raises(InvalidInput):
        await app.find_job("document.summarize", key)
    with pytest.raises(InvalidInput):
        await app.jobs(idempotency_key=key)


async def test_invalid_submissions_are_refused_and_not_recorded(
    unlaunched: tuple[Brevia, Launcher], store: MemoryStore
) -> None:
    app, _ = unlaunched
    with pytest.raises(InvalidInput):
        await app.submit("document.summarize", {"text": ""})
    with pytest.raises(OverrideNotAllowed):
        await app.submit("document.summarize", {"text": "A"}, {"model": "x"})
    with pytest.raises(InvalidInput):
        await app.submit("document.summarize", {"text": "A"}, {"language": object()})
    with pytest.raises(NotFound):
        await app.submit("not.registered", {"text": "A"})
    assert store.jobs == {}


async def test_jobs_need_a_backend_and_job_activities_at_start(
    tmp_path: Path, store: MemoryStore
) -> None:
    app = project_brevia(tmp_path, store, jobs=DbosBackend("sqlite:///x", "dbos"))
    async with app:
        with pytest.raises(RuntimeError, match="register activities before"):
            await app.submit("document.summarize", {"text": "A"})
    without = project_brevia(tmp_path, store, modes=("direct", "job"))
    with pytest.raises(RuntimeError, match="job backend"):
        without.job(str(uuid.uuid4()))


async def test_direct_only_activities_refuse_jobs(
    unlaunched: tuple[Brevia, Launcher],
) -> None:
    app, _ = unlaunched
    app.register_activity(
        name="test.direct-only",
        version="1",
        function=no_model,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=NoConfig,
    )
    with pytest.raises(Unsupported):
        await app.submit("test.direct-only", {"text": "A"})
    with pytest.raises(Unsupported):
        await app.run("test.held", {"text": "A"})


def test_job_activities_need_types_at_module_level(
    tmp_path: Path, store: MemoryStore
) -> None:
    class Local(BaseModel):
        text: str

    app = project_brevia(tmp_path, store)
    with pytest.raises(ValueError, match="module level"):
        app.register_activity(
            name="test.local",
            version="1",
            function=no_model,
            input_type=Local,
            output_type=SummaryResult,
            config_type=NoConfig,
            modes=("job",),
        )
    app.register_activity(
        name="test.local",
        version="1",
        function=no_model,
        input_type=Local,
        output_type=SummaryResult,
        config_type=NoConfig,
    )


async def test_unknown_or_malformed_job_identifiers_are_not_found(
    jobs: Brevia,
) -> None:
    with pytest.raises(NotFound):
        jobs.job("not-a-uuid")
    with pytest.raises(NotFound):
        await jobs.job(str(uuid.uuid4())).status()


# ---------- cancellation and retry ----------


async def test_a_running_job_is_cancelled(jobs: Brevia, store: MemoryStore) -> None:
    handle = await jobs.submit("test.held", {"text": "Un testo."})
    await asyncio.wait_for(GATE.entered.wait(), WAIT)
    state = await handle.cancel()
    assert state.status == "cancelled"
    assert state.error is not None
    assert state.error["code"] == "cancelled"
    assert (await handle.cancel()).status == "cancelled"
    # The engine stops the run, which records its cancellation without calls.
    await _until(lambda: uuid.UUID(handle.run_id) in store.outcomes)
    # The activity was stopped at the gate, before its model call.
    await asyncio.wait_for(GATE.left.wait(), WAIT)
    with simulated(answers({"summary": "Breve."})):
        GATE.release.set()
        with pytest.raises(Cancelled):
            await handle.result(wait=WAIT)
    # The model call after the cancellation did not run.
    assert store.calls_of(uuid.UUID(handle.run_id)) == []
    assert (await handle.status()).status == "cancelled"


async def test_a_cancellation_stops_a_call_in_progress_and_keeps_its_usage(
    jobs: Brevia, store: MemoryStore
) -> None:
    async def blocking(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        GATE.entered.set()
        await GATE.release.wait()
        raise AssertionError("not reached")

    with simulated(FunctionModel(blocking)):
        handle = await jobs.submit("document.summarize", {"text": "Un testo."})
        await asyncio.wait_for(GATE.entered.wait(), WAIT)
        await handle.cancel()
        await _until(lambda: uuid.UUID(handle.run_id) in store.outcomes)
    # The call was stopped while the model had not answered: it is recorded, with
    # the usage known so far (Pydantic AI counts a request when it is answered).
    (call,) = store.calls_of(uuid.UUID(handle.run_id))
    assert call.error == "cancelled"
    state = await handle.status()
    assert state.status == "cancelled"
    assert state.usage is not None
    assert state.usage["requests"] == call.requests


async def test_a_cancellation_is_recorded_before_the_engine_stops_the_run(
    jobs: Brevia, store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = await jobs.submit("test.held", {"text": "Un testo."})
    await asyncio.wait_for(GATE.entered.wait(), WAIT)
    backend = jobs._jobs_backend
    assert backend is not None
    seen: list[str] = []
    cancel = backend.cancel

    async def recording(run_id: str) -> None:
        seen.append(store.jobs[uuid.UUID(run_id)].status)
        await cancel(run_id)

    monkeypatch.setattr(backend, "cancel", recording)
    await handle.cancel()
    # The run stopped by the engine finds the job cancelled and adds its calls.
    assert seen == ["cancelled"]


async def test_a_job_already_ended_does_not_run_again(
    jobs: Brevia, store: MemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    handle = await jobs.submit("test.no-model", {"text": "eco"})
    await handle.result(wait=WAIT)
    record = store.jobs[uuid.UUID(handle.run_id)]
    assert record.snapshot is not None
    prepared = workflow.Prepared(
        SummaryRequest(text="eco"),
        NoConfig(),
        {},
        dict(record.snapshot),
        datetime.now(UTC) + timedelta(seconds=60),
    )
    caplog.clear()
    caplog.set_level(logging.INFO)
    # As an execution started again after the outcome was written.
    runtime = jobs._job_runtime
    assert runtime is not None
    await workflow._run(
        runtime, runtime.activity("test.no-model"), handle.run_id, prepared
    )
    assert not any(r.getMessage().startswith("Run started") for r in caplog.records)
    assert store.jobs[uuid.UUID(handle.run_id)] == record


async def test_a_queued_job_cancelled_never_starts(
    unlaunched: tuple[Brevia, Launcher], store: MemoryStore
) -> None:
    app, launched = unlaunched
    handle = await app.submit("test.no-model", {"text": "eco"})
    assert (await handle.status()).status == "queued"
    assert (await handle.cancel()).status == "cancelled"
    later = await app.submit("test.no-model", {"text": "dopo"})
    await launched()
    # The queue has run past the cancelled job once the job after it has ended.
    await later.result(wait=WAIT)
    record = store.jobs[uuid.UUID(handle.run_id)]
    assert record.status == "cancelled"
    assert record.started_at is None


async def test_a_cancellation_seen_only_by_the_engine_is_reconciled(
    unlaunched: tuple[Brevia, Launcher],
) -> None:
    app, _ = unlaunched
    handle = await app.submit("test.no-model", {"text": "eco"})
    backend = app._jobs_backend
    assert backend is not None
    await backend.cancel(handle.run_id)
    assert (await handle.status()).status == "cancelled"


async def test_a_failed_job_is_retried_as_a_linked_job(
    jobs: Brevia, store: MemoryStore
) -> None:
    invalid = {"wrong": "field"}
    with simulated(answers(invalid, invalid, invalid, {"summary": "Breve."})):
        failed = await jobs.submit(
            "document.summarize", {"text": "Un testo."}, {"language": "en"}
        )
        with pytest.raises(OutputInvalid):
            await failed.result(wait=WAIT)
        retried = await failed.retry()
        assert await retried.result(wait=WAIT) == SummaryResult(summary="Breve.")
    state = await retried.status()
    assert state.retry_of == failed.run_id
    record = store.jobs[uuid.UUID(retried.run_id)]
    assert record.overrides == {"language": "en"}
    assert record.input == {"text": "Un testo.", "language": None}


async def test_a_retried_job_keeps_the_caller_of_the_failed_one(
    jobs: Brevia, store: MemoryStore
) -> None:
    caller = Caller("backend", end_user="user-7")
    invalid = {"wrong": "field"}
    with simulated(answers(*[invalid] * 6)):  # three attempts for each job
        failed = await jobs.submit(
            "document.summarize", {"text": "Un testo."}, caller=caller
        )
        with pytest.raises(OutputInvalid):
            await failed.result(wait=WAIT)
        retried = await failed.retry()
        with pytest.raises(OutputInvalid):
            await retried.result(wait=WAIT)
    record = store.jobs[uuid.UUID(retried.run_id)]
    assert (record.caller, record.end_user) == ("backend", "user-7")


async def test_only_ended_and_unsuccessful_jobs_are_retried(jobs: Brevia) -> None:
    held = await jobs.submit("test.held", {"text": "Un testo."})
    await asyncio.wait_for(GATE.entered.wait(), WAIT)
    with pytest.raises(Busy):
        await held.retry()
    done = await jobs.submit("test.no-model", {"text": "eco"})
    await done.result(wait=WAIT)
    with pytest.raises(Unsupported):
        await done.retry()


# ---------- values fixed at the first step ----------


async def test_a_job_keeps_the_configuration_resolved_when_it_started(
    jobs: Brevia, store: MemoryStore
) -> None:
    handle = await jobs.submit("test.held", {"text": "Un testo."})
    await asyncio.wait_for(GATE.entered.wait(), WAIT)
    await jobs.customize_configuration("test.held", {"language": "en"})
    with simulated(answers({"summary": "Breve."})):
        GATE.release.set()
        assert await handle.result(wait=WAIT) == SummaryResult(summary="it: Breve.")
    record = store.jobs[uuid.UUID(handle.run_id)]
    assert record.snapshot is not None
    assert record.snapshot["config"]["language"] == "it"


async def test_a_queued_job_reads_the_customisations_when_it_starts(
    unlaunched: tuple[Brevia, Launcher],
) -> None:
    app, launched = unlaunched
    handle = await app.submit("test.held", {"text": "Un testo."})
    await app.customize_configuration("test.held", {"language": "en"})
    await launched()
    with simulated(answers({"summary": "Breve."})):
        GATE.release.set()
        assert await handle.result(wait=WAIT) == SummaryResult(summary="en: Breve.")


async def test_a_job_keeps_its_first_deadline(
    unlaunched: tuple[Brevia, Launcher], store: MemoryStore
) -> None:
    app, launched = unlaunched
    handle = await app.submit("test.no-model", {"text": "eco"})
    key = uuid.UUID(handle.run_id)
    past = datetime.now(UTC) - timedelta(seconds=1)
    store.jobs[key] = replace(store.jobs[key], deadline_at=past)
    await launched()
    with pytest.raises(RunTimeout):
        await handle.result(wait=WAIT)
    assert store.jobs[key].deadline_at == past


async def test_a_job_of_another_activity_version_fails_to_be_retried(
    unlaunched: tuple[Brevia, Launcher],
) -> None:
    app, launched = unlaunched
    handle = await app.submit("test.no-model", {"text": "eco"})
    activity = app._activities["test.no-model"]
    app._activities["test.no-model"] = replace(activity, version="2")
    await launched()
    with pytest.raises(Unsupported) as caught:
        await handle.result(wait=WAIT)
    assert caught.value.retryable
    retried = await handle.retry()
    assert await retried.result(wait=WAIT) == SummaryResult(summary="eco")
    assert (await retried.status()).activity_version == "2"


async def test_new_jobs_run_after_a_rollback_to_an_earlier_version(
    unlaunched: tuple[Brevia, Launcher],
) -> None:
    app, _ = unlaunched
    backend = app._jobs_backend
    assert isinstance(backend, DbosBackend)
    for index, version in enumerate(("v1", "v2", "v1")):
        if index:  # the last worker is stopped by the fixture
            await asyncio.to_thread(DBOS.destroy, workflow_completion_timeout_sec=0)
        launch(app, backend, version, "unit-worker")
        await DBOS.register_queue_async(QUEUE, polling_interval_sec=0.05)
        handle = await app.submit("test.no-model", {"text": version})
        assert await handle.result(wait=WAIT) == SummaryResult(summary=version)


async def test_a_job_stopped_with_its_worker_starts_again_from_the_beginning(
    jobs: Brevia, store: MemoryStore
) -> None:
    handle = await jobs.submit("test.held", {"text": "Un testo."})
    await asyncio.wait_for(GATE.entered.wait(), WAIT)
    await _stop_worker()
    # The stop records nothing: the job is still running.
    assert store.jobs[uuid.UUID(handle.run_id)].status == "running"
    await jobs.customize_configuration("test.held", {"language": "en"})
    GATE.reset()
    GATE.release.set()
    with simulated(answers({"summary": "Breve."})):
        launch(jobs, jobs._jobs_backend, VERSION, "unit-worker")  # type: ignore[arg-type]
        await DBOS.register_queue_async(QUEUE, polling_interval_sec=0.05)
        result = await handle.result(wait=WAIT)
    # The values resolved at the first start, and the calls of the last execution.
    assert result == SummaryResult(summary="it: Breve.")
    assert len(store.calls_of(uuid.UUID(handle.run_id))) == 1


async def test_a_job_started_again_with_another_activity_version_fails(
    jobs: Brevia, store: MemoryStore
) -> None:
    # Same engine version, new code of the activity: the first step comes from the
    # checkpoint, so the version is checked again before the activity runs.
    handle = await jobs.submit("test.held", {"text": "Un testo."})
    await asyncio.wait_for(GATE.entered.wait(), WAIT)
    await _stop_worker()
    activity = jobs._activities["test.held"]
    jobs._activities["test.held"] = replace(activity, version="2")
    GATE.reset()
    GATE.release.set()
    with simulated(answers({"summary": "Breve."})):
        launch(jobs, jobs._jobs_backend, VERSION, "unit-worker")  # type: ignore[arg-type]
        await DBOS.register_queue_async(QUEUE, polling_interval_sec=0.05)
        with pytest.raises(Unsupported) as caught:
            await handle.result(wait=WAIT)
    assert caught.value.retryable
    assert caught.value.details == {"version": "2", "submitted": "1"}
    assert not GATE.entered.is_set()  # the new code did not run
    assert store.calls_of(uuid.UUID(handle.run_id)) == []


async def test_a_job_stopped_too_many_times_fails(
    jobs: Brevia, store: MemoryStore
) -> None:
    handle = await jobs.submit("test.held", {"text": "Un testo."})
    for _ in range(workflow.MAX_RESTARTS + 1):
        await asyncio.wait_for(GATE.entered.wait(), WAIT)
        await _stop_worker()
        GATE.reset()
        launch(jobs, jobs._jobs_backend, VERSION, "unit-worker")  # type: ignore[arg-type]
        await DBOS.register_queue_async(QUEUE, polling_interval_sec=0.05)
    await _status_becomes(jobs, handle.run_id, "failed")


async def test_the_cleanup_records_how_a_job_ended_before_deleting_its_steps(
    unlaunched: tuple[Brevia, Launcher], store: MemoryStore
) -> None:
    app, _ = unlaunched
    handle = await app.submit("test.no-model", {"text": "eco"})
    backend = app._jobs_backend
    assert backend is not None
    await backend.cancel(handle.run_id)  # ended in the engine, record still queued
    later = datetime.now(UTC) + timedelta(days=31)
    cleaned = await clean(store, backend, 30, now=later)
    assert cleaned.job_steps == 1
    assert await backend.status(handle.run_id) is None
    state = store.jobs[uuid.UUID(handle.run_id)]
    assert state.status == "cancelled"
    retried = await handle.retry()
    assert (await retried.status()).status == "queued"


async def test_without_retention_the_steps_of_ended_jobs_are_kept(
    unlaunched: tuple[Brevia, Launcher], store: MemoryStore
) -> None:
    app, _ = unlaunched
    handle = await app.submit("test.no-model", {"text": "eco"})
    backend = app._jobs_backend
    assert backend is not None
    await backend.cancel(handle.run_id)
    later = datetime.now(UTC) + timedelta(days=3650)
    cleaned = await clean(store, backend, 0, now=later)
    assert cleaned.job_steps == 0
    assert await backend.status(handle.run_id) is not None


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


async def test_the_example_of_the_guide_runs_as_a_job(
    tmp_path: Path, store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    guide = (Path(__file__).parents[2] / "docs" / "guides" / "jobs.md").read_text()
    code = guide.split("## Writing an activity that can start again")[1]
    code = code.split("```python\n")[1].split("```")[0]
    (tmp_path / "guide_report.py").write_text(code, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    example = importlib.import_module("guide_report")
    url = f"sqlite:///{tmp_path / 'jobs.sqlite'}"
    DBOS.migrate(url)
    backend = DbosBackend(url, "dbos")
    app = project_brevia(tmp_path, store, jobs=backend)
    app.register_activity(
        name="test.custom",
        version="1",
        function=example.report,
        input_type=example.ReportRequest,
        output_type=example.Report,
        config_type=example.ReportConfig,
        modes=("job",),
    )
    await app.start()
    launch(app, backend, VERSION, "unit-worker")
    await DBOS.register_queue_async(QUEUE, polling_interval_sec=0.05)
    try:
        with simulated(answers({"summary": "Uno."}, {"summary": "Due."})):
            handle = await app.submit(
                "test.custom",
                {
                    "sections": [
                        {"title": "A", "text": "a"},
                        {"title": "B", "text": "b"},
                    ]
                },
            )
            report = await handle.result(wait=WAIT)
    finally:
        await asyncio.to_thread(DBOS.destroy, workflow_completion_timeout_sec=0)
        workflow.install(None)
        await app.stop()
    written = Path(report.model_dump()["path"])
    assert written.name == f"{handle.run_id}.md"
    assert _text(written) == "Uno.\n\nDue."


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


async def test_a_step_stopped_during_a_call_logs_no_contents(jobs: Brevia) -> None:
    user_text = "TESTO-RISERVATO"

    async def blocking(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        GATE.entered.set()
        await GATE.release.wait()
        raise AssertionError("not reached")

    handler = _Records()
    logging.getLogger("dbos").addHandler(handler)
    try:
        with simulated(FunctionModel(blocking)):
            await jobs.submit("document.summarize", {"text": user_text})
            await asyncio.wait_for(GATE.entered.wait(), WAIT)
            await _stop_running_jobs()  # as a worker that stops during the call
    finally:
        logging.getLogger("dbos").removeHandler(handler)
    messages = [record.getMessage() for record in handler.records]
    assert any("cancelled" in message for message in messages)
    assert not any(user_text in message for message in messages)


# ---------- the worker command ----------


def test_without_an_application_version_workers_use_the_version_of_brevia(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setenv("BREVIA_DATABASE_URL", "postgresql://u:p@db/brevia")
    monkeypatch.delenv("BREVIA_APP_VERSION", raising=False)
    assert engine_version(BreviaSettings()) == f"brevia-{__version__}"  # type: ignore[call-arg]
    monkeypatch.setenv("BREVIA_APP_VERSION", "2026.10.1")
    assert engine_version(BreviaSettings()) == "2026.10.1"  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("version", "reference", "message"),
    [
        (None, "os:sep", "is not a Brevia application"),
        ("1", "no_such_module_here:app", "cannot load the application"),
        ("1", "os", "MODULE:NAME"),
        ("1", "os:sep", "is not a Brevia application"),
    ],
)
def test_the_worker_command_refuses_what_it_cannot_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    version: str | None,
    reference: str,
    message: str,
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setenv("BREVIA_DATABASE_URL", "postgresql://u:p@db/brevia")
    if version is None:
        monkeypatch.delenv("BREVIA_APP_VERSION", raising=False)
    else:
        monkeypatch.setenv("BREVIA_APP_VERSION", version)
    assert main(["worker", reference]) == 2
    assert message in capsys.readouterr().err
