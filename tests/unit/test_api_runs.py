"""HTTP API: activities and runs, direct and as jobs.

Jobs run as in the unit tests of jobs: DBOS in this process on SQLite, with the store
in memory. The app is called in the event loop of the test, with Brevia already
started, so that the worker of the test runs the jobs it submits.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest
from conftest import answers, project_brevia, simulated
from dbos import DBOS
from memory_store import MemoryStore
from pydantic import BaseModel, Field, RootModel, SecretStr, computed_field
from summary_example import NoConfig, SummaryRequest

from brevia import (
    Brevia,
    Caller,
    FileRef,
    FileStore,
    OutputInvalid,
    RunContext,
    create_token,
)
from brevia.access.auth import AuthSettings
from brevia.api import create_app
from brevia.jobs import workflow
from brevia.jobs.backend import QUEUE, DbosBackend
from brevia.jobs.worker import launch

pytestmark = pytest.mark.unit

SECRET = "s" * 32
WAIT = 10


class NoteResult(BaseModel):
    note: FileRef


async def write_note(request: SummaryRequest, ctx: RunContext[NoConfig]) -> NoteResult:
    return NoteResult(note=await ctx.files.save("note.txt", request.text.encode()))


async def invalid_output(
    request: SummaryRequest, ctx: RunContext[NoConfig]
) -> NoteResult:
    raise OutputInvalid("The output is not valid", {"attempts": 2})


Launcher = Callable[[], Awaitable[None]]


@pytest.fixture
async def started(
    tmp_path: Path, store: MemoryStore
) -> AsyncIterator[tuple[Brevia, Launcher]]:
    """A started Brevia with jobs, and the function that launches its worker."""
    url = f"sqlite:///{tmp_path / 'jobs.sqlite'}"
    DBOS.migrate(url)
    backend = DbosBackend(url, "dbos")
    files = FileStore(tmp_path / "files")
    app = project_brevia(
        tmp_path, store, modes=("direct", "job"), jobs=backend, files=files
    )
    for name, function in (("test.note", write_note), ("test.invalid", invalid_output)):
        app.register_activity(
            name=name,
            version="1",
            function=function,
            input_type=SummaryRequest,
            output_type=NoteResult,
            config_type=NoConfig,
            modes=("job",),
        )
    await app.start()

    async def launched() -> None:
        launch(app, backend, "test-1", "unit-worker")
        await DBOS.register_queue_async(QUEUE, polling_interval_sec=0.05)

    try:
        yield app, launched
    finally:
        await asyncio.to_thread(DBOS.destroy, workflow_completion_timeout_sec=0)
        workflow.install(None)
        await app.stop()


def client_of(app: Brevia, user: str | None = "bedita") -> httpx2.AsyncClient:
    """A client of the HTTP app of ``app``, with the token of ``user``.

    The transport does not run the lifespan: Brevia is started by the fixture.
    """
    settings = AuthSettings(
        tokens_secret=SecretStr(SECRET),
        tokens_users="",
        auth_disabled=False,
        status_token=None,
    )
    headers = {}
    if user is not None:
        headers["Authorization"] = f"Bearer {create_token(user, 5, SECRET)}"
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=create_app(app, settings)),
        base_url="http://test",
        headers=headers,
    )


@pytest.fixture
async def queued(
    started: tuple[Brevia, Launcher],
) -> AsyncIterator[httpx2.AsyncClient]:
    """A client of an app whose jobs stay queued: no worker runs them."""
    async with client_of(started[0]) as client:
        yield client


@pytest.fixture
async def client(
    started: tuple[Brevia, Launcher],
) -> AsyncIterator[httpx2.AsyncClient]:
    """A client of an app whose worker runs the jobs."""
    await started[1]()
    async with client_of(started[0]) as test_client:
        yield test_client


def assert_error(response: httpx2.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    assert body["code"] == code
    assert set(body) == {"code", "message", "details", "request_id"}
    return body


async def submit(
    client: httpx2.AsyncClient, activity: str = "test.note", **values: Any
) -> dict[str, Any]:
    body = {"activity": activity, "input": {"text": "Una nota."}} | values
    response = await client.post("/runs", json=body)
    assert response.status_code == 202, response.text
    state: dict[str, Any] = response.json()
    assert response.headers["Location"] == f"http://test/runs/{state['run_id']}"
    return state


async def ended(client: httpx2.AsyncClient, run_id: str) -> dict[str, Any]:
    for _ in range(WAIT * 20):
        state: dict[str, Any] = (await client.get(f"/runs/{run_id}")).json()
        if state["status"] in ("succeeded", "failed", "cancelled"):
            return state
        await asyncio.sleep(0.05)
    raise AssertionError("the job did not end")


# ---------- activities ----------


async def test_activities_are_listed_by_name(queued: httpx2.AsyncClient) -> None:
    response = await queued.get("/activities")
    assert response.json() == [
        {"name": "document.summarize", "version": "1", "modes": ["direct", "job"]},
        {"name": "test.invalid", "version": "1", "modes": ["job"]},
        {"name": "test.note", "version": "1", "modes": ["job"]},
    ]


async def test_an_activity_shows_its_schemas_and_overrides(
    queued: httpx2.AsyncClient,
) -> None:
    body = (await queued.get("/activities/document.summarize")).json()
    assert body["overridable"] == ["language"]
    assert body["input_schema"] == SummaryRequest.model_json_schema()
    assert body["output_schema"]["properties"] == {
        "summary": {"title": "Summary", "type": "string"}
    }
    assert_error(await queued.get("/activities/missing"), 404, "not_found")


async def test_activities_and_runs_need_a_token(
    started: tuple[Brevia, Launcher],
) -> None:
    async with client_of(started[0], user=None) as anonymous:
        assert_error(await anonymous.get("/activities"), 401, "unauthorized")
        assert_error(await anonymous.get("/runs/x"), 401, "unauthorized")
        response = await anonymous.post(
            "/runs", json={"activity": "test.note", "input": {"text": "x"}}
        )
        assert_error(response, 401, "unauthorized")


# ---------- direct runs ----------


async def test_a_direct_run_answers_with_its_identifier_and_output(
    queued: httpx2.AsyncClient, store: MemoryStore
) -> None:
    body = {
        "activity": "document.summarize",
        "input": {"text": "Un testo."},
        "mode": "direct",
    }
    with simulated(answers({"summary": "Breve."})):
        response = await queued.post("/runs", json=body)
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"run_id", "status", "output"}
    assert (result["status"], result["output"]) == ("succeeded", {"summary": "Breve."})
    # The identifier of the recorded run: feedback can be added to it.
    (run,) = store.runs.values()
    assert str(run.id) == result["run_id"]
    rating = {"kind": "rating", "rating": "good"}
    feedback = await queued.post(f"/runs/{result['run_id']}/feedback", json=rating)
    assert feedback.status_code == 201


async def test_the_mode_is_required_only_with_two_modes(
    queued: httpx2.AsyncClient,
) -> None:
    body = {"activity": "document.summarize", "input": {"text": "Un testo."}}
    error = assert_error(await queued.post("/runs", json=body), 422, "invalid_input")
    assert error["details"]["modes"] == ["direct", "job"]
    # One mode only: it is the default.
    assert (await submit(queued, "test.note"))["status"] == "queued"


async def test_a_direct_run_refuses_an_idempotency_key(
    queued: httpx2.AsyncClient,
) -> None:
    body = {"activity": "document.summarize", "input": {"text": "x"}, "mode": "direct"}
    response = await queued.post("/runs", json=body, headers={"Idempotency-Key": "k"})
    assert_error(response, 422, "invalid_input")


async def test_errors_of_the_request_keep_their_code(
    queued: httpx2.AsyncClient,
) -> None:
    unknown = {"activity": "missing", "input": {}}
    assert_error(await queued.post("/runs", json=unknown), 404, "not_found")
    direct = {"activity": "test.note", "input": {"text": "x"}, "mode": "direct"}
    assert_error(await queued.post("/runs", json=direct), 422, "unsupported")
    invalid = {"activity": "test.note", "input": {"text": ""}}
    assert_error(await queued.post("/runs", json=invalid), 422, "invalid_input")
    override = {
        "activity": "document.summarize",
        "input": {"text": "x"},
        "overrides": {"model": "other"},
        "mode": "job",
    }
    response = await queued.post("/runs", json=override)
    assert_error(response, 422, "override_not_allowed")
    extra = {"activity": "test.note", "input": {"text": "x"}, "wait": 10}
    assert_error(await queued.post("/runs", json=extra), 422, "invalid_input")


# ---------- jobs ----------


async def test_a_job_is_accepted_at_once_and_not_ready_until_it_ends(
    queued: httpx2.AsyncClient,
) -> None:
    state = await submit(queued)
    assert state["activity"] == "test.note"
    assert state["status"] == "queued"
    assert state["started_at"] is None
    run_id = state["run_id"]
    assert (await queued.get(f"/runs/{run_id}")).json() == state
    error = assert_error(await queued.get(f"/runs/{run_id}/result"), 409, "not_ready")
    assert error["details"] == {"run_id": run_id, "status": "queued"}


async def test_a_job_gives_its_output_and_its_files(
    client: httpx2.AsyncClient,
) -> None:
    run_id = (await submit(client))["run_id"]
    state = await ended(client, run_id)
    assert state["status"] == "succeeded"
    assert state["usage"]["requests"] == 0
    output = (await client.get(f"/runs/{run_id}/result")).json()
    assert output["note"]["name"] == "note.txt"
    response = await client.get(f"/runs/{run_id}/files/note.txt")
    assert response.status_code == 200
    assert response.content == b"Una nota."
    assert "note.txt" in response.headers["Content-Disposition"]
    missing = await client.get(f"/runs/{run_id}/files/other.txt")
    assert_error(missing, 404, "not_found")
    escaping = await client.get(f"/runs/{run_id}/files/..%2F..%2Fjobs.sqlite")
    assert_error(escaping, 404, "not_found")


async def test_a_failed_job_answers_409_with_its_error(
    client: httpx2.AsyncClient,
) -> None:
    run_id = (await submit(client, "test.invalid"))["run_id"]
    state = await ended(client, run_id)
    assert state["status"] == "failed"
    assert state["error"]["code"] == "output_invalid"
    response = await client.get(f"/runs/{run_id}/result")
    # Not 500, the status of OutputInvalid: reading the result did not fail.
    error = assert_error(response, 409, "output_invalid")
    assert error["message"] == "The output is not valid"
    assert error["details"] == {"attempts": 2, "run_id": run_id, "retryable": False}


async def test_the_same_idempotency_key_gives_the_same_job(
    queued: httpx2.AsyncClient,
) -> None:
    key = {"Idempotency-Key": "doc-1"}
    body = {"activity": "test.note", "input": {"text": "Una nota."}}
    first = await queued.post("/runs", json=body, headers=key)
    second = await queued.post("/runs", json=body, headers=key)
    assert first.status_code == second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]
    other = {"activity": "test.note", "input": {"text": "Un'altra nota."}}
    response = await queued.post("/runs", json=other, headers=key)
    assert_error(response, 409, "idempotency_conflict")


async def test_a_job_is_cancelled_and_retried(queued: httpx2.AsyncClient) -> None:
    run_id = (await submit(queued))["run_id"]
    error = assert_error(await queued.post(f"/runs/{run_id}/retry"), 409, "busy")
    assert error["details"] == {"status": "queued"}

    cancelled = await queued.post(f"/runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    again = await queued.post(f"/runs/{run_id}/cancel")
    assert again.json()["status"] == "cancelled"
    result = await queued.get(f"/runs/{run_id}/result")
    assert_error(result, 409, "cancelled")

    retried = await queued.post(f"/runs/{run_id}/retry")
    assert retried.status_code == 202
    state = retried.json()
    assert state["retry_of"] == run_id
    assert state["status"] == "queued"
    assert retried.headers["Location"] == f"http://test/runs/{state['run_id']}"


async def test_a_caller_does_not_see_the_jobs_of_another(
    started: tuple[Brevia, Launcher], queued: httpx2.AsyncClient
) -> None:
    run_id = (await submit(queued))["run_id"]
    async with client_of(started[0], user="other") as other:
        for response in (
            await other.get(f"/runs/{run_id}"),
            await other.get(f"/runs/{run_id}/result"),
            await other.post(f"/runs/{run_id}/cancel"),
            await other.post(f"/runs/{run_id}/retry"),
            await other.get(f"/runs/{run_id}/files/note.txt"),
        ):
            assert_error(response, 404, "not_found")
    assert (await queued.get(f"/runs/{run_id}")).json()["status"] == "queued"


async def test_an_identifier_that_is_not_a_job_is_not_found(
    queued: httpx2.AsyncClient,
) -> None:
    assert_error(await queued.get("/runs/not-a-uuid"), 404, "not_found")


# ---------- list of jobs ----------


async def test_jobs_are_listed_in_pages_newest_first(
    queued: httpx2.AsyncClient,
) -> None:
    submitted = [(await submit(queued))["run_id"] for _ in range(3)]
    first = (await queued.get("/runs", params={"limit": 2})).json()
    assert len(first["jobs"]) == 2
    assert first["next_cursor"] is not None
    params = {"limit": 2, "cursor": first["next_cursor"]}
    second = (await queued.get("/runs", params=params)).json()
    assert second["next_cursor"] is None
    listed = [job["run_id"] for job in first["jobs"] + second["jobs"]]
    assert sorted(listed) == sorted(submitted)
    assert listed[0] == submitted[-1]
    assert first["jobs"][0] == (await queued.get(f"/runs/{listed[0]}")).json()


async def test_jobs_are_filtered(queued: httpx2.AsyncClient) -> None:
    note = (await submit(queued))["run_id"]
    invalid = (await submit(queued, "test.invalid"))["run_id"]
    await queued.post(f"/runs/{invalid}/cancel")

    async def listed(**params: Any) -> list[str]:
        body = (await queued.get("/runs", params=params)).json()
        return [job["run_id"] for job in body["jobs"]]

    assert await listed(activity="test.note") == [note]
    assert await listed(status="cancelled") == [invalid]
    assert await listed(status="queued", activity="test.invalid") == []


async def test_the_job_of_a_key_is_found_without_submitting_it(
    started: tuple[Brevia, Launcher], queued: httpx2.AsyncClient
) -> None:
    body = {"activity": "test.note", "input": {"text": "Una nota."}}
    response = await queued.post("/runs", json=body, headers={"Idempotency-Key": "k"})
    run_id = response.json()["run_id"]
    params = {"activity": "test.note", "idempotency_key": "k"}
    found = (await queued.get("/runs", params=params)).json()["jobs"]
    assert [job["run_id"] for job in found] == [run_id]
    missing = {"activity": "test.note", "idempotency_key": "other"}
    assert (await queued.get("/runs", params=missing)).json()["jobs"] == []
    # The same lookup from Python, scoped to the caller of the key.
    app = started[0]
    state = await app.find_job("test.note", "k", caller=Caller("bedita"))
    assert state is not None
    assert state.run_id == run_id
    assert await app.find_job("test.note", "k", caller=Caller("other")) is None
    assert await app.find_job("test.note", "k") is None  # trusted code: own keys


async def test_a_caller_lists_only_its_own_jobs(
    started: tuple[Brevia, Launcher], queued: httpx2.AsyncClient
) -> None:
    mine = (await submit(queued))["run_id"]
    async with client_of(started[0], user="other") as other:
        theirs = (await submit(other))["run_id"]
        listed = (await other.get("/runs")).json()["jobs"]
        assert [job["run_id"] for job in listed] == [theirs]
    # Trusted code in the process lists every job.
    page = await started[0].jobs()
    assert {state.run_id for state in page.jobs} == {mine, theirs}


async def test_a_wrong_limit_or_cursor_is_refused(queued: httpx2.AsyncClient) -> None:
    for params in ({"limit": 0}, {"limit": 101}, {"status": "lost"}):
        response = await queued.get("/runs", params=params)
        assert_error(response, 422, "invalid_input")
    for cursor in ("not-a-cursor", "bm90IGEgY3Vyc29y"):
        response = await queued.get("/runs", params={"cursor": cursor})
        assert_error(response, 422, "invalid_input")


async def test_a_listed_job_ended_in_the_engine_is_reconciled(
    started: tuple[Brevia, Launcher], store: MemoryStore, queued: httpx2.AsyncClient
) -> None:
    run_id = (await submit(queued))["run_id"]
    backend = started[0]._jobs_backend
    assert backend is not None
    await backend.cancel(run_id)  # ended in the engine only
    assert store.jobs[uuid.UUID(run_id)].status == "queued"
    (listed,) = (await queued.get("/runs")).json()["jobs"]
    assert listed["status"] == "cancelled"


# ---------- applications without jobs, outputs with aliases ----------


class Labelled(BaseModel):
    label_text: str = Field(alias="labelText")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def length(self) -> int:
        return len(self.label_text)


async def label(request: SummaryRequest, ctx: RunContext[NoConfig]) -> Labelled:
    return Labelled(labelText=request.text)


class Words(RootModel[list[str]]):
    """An output that is not an object."""


async def split_words(request: SummaryRequest, ctx: RunContext[NoConfig]) -> Words:
    return Words(request.text.split())


@pytest.fixture
async def direct_only(
    tmp_path: Path, store: MemoryStore
) -> AsyncIterator[httpx2.AsyncClient]:
    """A client of an app whose activities are direct only: it has no jobs."""
    app = project_brevia(tmp_path, store)
    app.register_activity(
        name="test.label",
        version="1",
        function=label,
        input_type=SummaryRequest,
        output_type=Labelled,
        config_type=NoConfig,
    )
    app.register_activity(
        name="test.words",
        version="1",
        function=split_words,
        input_type=SummaryRequest,
        output_type=Words,
        config_type=NoConfig,
    )
    await app.start()
    try:
        async with client_of(app) as test_client:
            yield test_client
    finally:
        await app.stop()


async def test_the_output_schema_describes_the_returned_json(
    direct_only: httpx2.AsyncClient,
) -> None:
    schema = (await direct_only.get("/activities/test.label")).json()["output_schema"]
    assert set(schema["properties"]) == {"labelText", "length"}
    body = {"activity": "test.label", "input": {"text": "nota"}}
    output = (await direct_only.post("/runs", json=body)).json()["output"]
    assert output == {"labelText": "nota", "length": 4}
    assert set(output) == set(schema["properties"])


async def test_without_jobs_a_job_is_not_found(
    direct_only: httpx2.AsyncClient,
) -> None:
    run_id = str(uuid.uuid4())
    for response in (
        await direct_only.get(f"/runs/{run_id}"),
        await direct_only.get(f"/runs/{run_id}/result"),
        await direct_only.post(f"/runs/{run_id}/cancel"),
        await direct_only.post(f"/runs/{run_id}/retry"),
        await direct_only.get(f"/runs/{run_id}/files/note.txt"),
    ):
        assert_error(response, 404, "not_found")
    listed = await direct_only.get("/runs")
    assert listed.json() == {"jobs": [], "next_cursor": None}


async def test_the_status_filter_sees_the_statuses_reconciled(
    started: tuple[Brevia, Launcher], store: MemoryStore, queued: httpx2.AsyncClient
) -> None:
    ended = (await submit(queued))["run_id"]
    waiting = (await submit(queued))["run_id"]
    backend = started[0]._jobs_backend
    assert backend is not None
    await backend.cancel(ended)  # ended in the engine only
    assert store.jobs[uuid.UUID(ended)].status == "queued"

    async def listed(status: str) -> list[str]:
        body = (await queued.get("/runs", params={"status": status})).json()
        assert all(job["status"] == status for job in body["jobs"])
        return [job["run_id"] for job in body["jobs"]]

    # Filtered first: the job is not hidden from its status, nor shown in its old one.
    assert await listed("cancelled") == [ended]
    assert await listed("queued") == [waiting]


async def test_a_job_records_the_end_user_of_the_caller(
    queued: httpx2.AsyncClient, store: MemoryStore
) -> None:
    body = {
        "activity": "test.note",
        "input": {"text": "Una nota."},
        "end_user": "user-42",
    }
    response = await queued.post("/runs", json=body)
    record = store.jobs[uuid.UUID(response.json()["run_id"])]
    assert (record.caller, record.end_user) == ("bedita", "user-42")
    invalid = body | {"end_user": " "}
    error = assert_error(await queued.post("/runs", json=invalid), 422, "invalid_input")
    assert error["details"] == {"field": "end_user"}
    assert len(store.jobs) == 1


async def test_a_direct_run_records_the_end_user_of_the_caller(
    queued: httpx2.AsyncClient, store: MemoryStore
) -> None:
    body = {
        "activity": "document.summarize",
        "input": {"text": "Un testo."},
        "mode": "direct",
        "end_user": "user-42",
    }
    with simulated(answers({"summary": "Breve."})):
        assert (await queued.post("/runs", json=body)).status_code == 200
    (run,) = store.runs.values()
    assert (run.caller, run.end_user) == ("bedita", "user-42")


# ---------- feedback ----------


async def test_feedback_is_added_to_a_job(
    started: tuple[Brevia, Launcher], queued: httpx2.AsyncClient, store: MemoryStore
) -> None:
    run_id = (await submit(queued))["run_id"]
    body = {
        "kind": "correction",
        "items": [{"target": "note", "original": "Una nota.", "corrected": "Nota."}],
        "comment": "Più breve.",
        "external_ref": {"system": "bedita", "object_id": "42"},
        "end_user": "user-42",
    }
    response = await queued.post(f"/runs/{run_id}/feedback", json=body)
    assert response.status_code == 201, response.text
    feedback = response.json()
    assert feedback["run_id"] == run_id
    assert (feedback["caller"], feedback["end_user"]) == ("bedita", "user-42")
    assert feedback["items"] == body["items"]
    (record,) = store.feedback
    assert str(record.id) == feedback["id"]

    rating = {"kind": "rating", "rating": "good"}
    assert (
        await queued.post(f"/runs/{run_id}/feedback", json=rating)
    ).status_code == 201
    assert len(store.feedback) == 2

    async with client_of(started[0], user="other") as other:
        response = await other.post(f"/runs/{run_id}/feedback", json=rating)
        assert_error(response, 404, "not_found")
    assert len(store.feedback) == 2


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "correction", "items": []},
        {"kind": "rating", "rating": "excellent"},
        {"kind": "rating", "rating": "good", "end_user": " "},
        {"kind": "rating", "rating": "good", "comment": "a\u0000b"},
    ],
)
async def test_invalid_feedback_is_refused_over_http(
    queued: httpx2.AsyncClient, store: MemoryStore, body: dict[str, Any]
) -> None:
    run_id = (await submit(queued))["run_id"]
    response = await queued.post(f"/runs/{run_id}/feedback", json=body)
    assert_error(response, 422, "invalid_input")
    assert store.feedback == []


async def test_feedback_on_a_missing_run_is_not_found(
    direct_only: httpx2.AsyncClient,
) -> None:
    rating = {"kind": "rating", "rating": "good"}
    for run_id in (str(uuid.uuid4()), "not-a-run"):
        response = await direct_only.post(f"/runs/{run_id}/feedback", json=rating)
        assert_error(response, 404, "not_found")


async def test_feedback_with_a_key_is_recorded_once_over_http(
    queued: httpx2.AsyncClient, store: MemoryStore
) -> None:
    run_id = (await submit(queued))["run_id"]
    key = {"Idempotency-Key": "doc-42-v3"}
    rating = {"kind": "rating", "rating": "good", "source": "reviewer"}
    first = await queued.post(f"/runs/{run_id}/feedback", json=rating, headers=key)
    again = await queued.post(f"/runs/{run_id}/feedback", json=rating, headers=key)
    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    assert first.json()["source"] == "reviewer"
    assert len(store.feedback) == 1
    other = rating | {"rating": "bad"}
    response = await queued.post(f"/runs/{run_id}/feedback", json=other, headers=key)
    error = assert_error(response, 409, "idempotency_conflict")
    assert error["details"] == {"feedback_id": first.json()["id"]}


async def test_an_output_that_is_not_an_object_is_returned_and_documented(
    direct_only: httpx2.AsyncClient,
) -> None:
    body = {"activity": "test.words", "input": {"text": "una nota breve"}}
    response = await direct_only.post("/runs", json=body)
    assert response.status_code == 200
    assert response.json()["output"] == ["una", "nota", "breve"]
    schemas = (await direct_only.get("/openapi.json")).json()["components"]["schemas"]
    # Any JSON value: no type that would refuse a list or a scalar.
    assert "type" not in schemas["DirectRun"]["properties"]["output"]


async def test_a_failed_direct_run_answers_422_with_its_identifier(
    queued: httpx2.AsyncClient, store: MemoryStore
) -> None:
    body = {"activity": "document.summarize", "input": {"text": "x"}, "mode": "direct"}
    invalid = answers({"wrong": 1}, {"wrong": 2}, {"wrong": 3})
    with simulated(invalid):
        response = await queued.post("/runs", json=body)
    # Not a server error: clients and proxies would repeat it, calling the model again.
    error = assert_error(response, 422, "output_invalid")
    (run,) = store.runs.values()
    assert error["details"]["run_id"] == str(run.id)
    rating = {"kind": "rating", "rating": "bad"}
    feedback = await queued.post(f"/runs/{run.id}/feedback", json=rating)
    assert feedback.status_code == 201
