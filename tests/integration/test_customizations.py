"""Customisations, prompt history and call contents on a real PostgreSQL database."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage
from sqlalchemy import Connection, select, text

from brevia import Brevia, OutputInvalid, RunContext, VersionConflict
from brevia.config.project import load_project
from brevia.db import migrate
from brevia.db.engine import sync_engine
from brevia.db.store import SqlStore
from brevia.db.tables import SCHEMA, model_calls, runs, trace_contents
from brevia.models import pydantic_ai as adapter_module
from integration.support import MODEL, Answer, Question, settings_for

pytestmark = pytest.mark.integration

PROJECT = f"""
[models."{MODEL}"]
prices = {{ input = 1, output = 2 }}

[activities."test.custom"]
model = "{MODEL}"

[activities."test.three"]
model = "{MODEL}"

[traces]
retention_days = 3
"""
PROMPT = "Answer in {language}."


class CustomConfig(BaseModel):
    model: str
    language: str = "it"
    max_words: int = 50


async def answer(request: Question, ctx: RunContext[CustomConfig]) -> Answer:
    result: Answer = await ctx.model().generate(
        instructions=ctx.prompt("answer").render(language=ctx.config.language),
        user_text=request.text,
        output_type=Answer,
    )
    return result


def model() -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"answer": "Yes."})],
            usage=RequestUsage(input_tokens=10, output_tokens=2),
        )

    return FunctionModel(respond)


@contextlib.asynccontextmanager
async def started(
    database_url: str, schema: str, tmp_path: Path, project: str = PROJECT
) -> AsyncIterator[Brevia]:
    migrate.upgrade(database_url, schema)
    (tmp_path / "brevia.toml").write_text(project, encoding="utf-8")
    (tmp_path / "answer.md").write_text(PROMPT, encoding="utf-8")
    brevia = Brevia(
        load_project(tmp_path / "brevia.toml"),
        project_dir=tmp_path,
        store=SqlStore(settings_for(database_url, schema)),
    )
    brevia.register_activity(
        name="test.custom",
        version="1",
        function=answer,
        input_type=Question,
        output_type=Answer,
        config_type=CustomConfig,
        prompts={"answer": "answer.md"},
        customizable=["language", "max_words"],
        capture="full",
    )
    async with brevia:
        yield brevia


@pytest.fixture
async def app(database_url: str, schema: str, tmp_path: Path) -> AsyncIterator[Brevia]:
    async with started(database_url, schema, tmp_path) as brevia:
        yield brevia


async def test_concurrent_changes_with_the_same_version_conflict(app: Brevia) -> None:
    results = await asyncio.gather(
        app.customize_configuration(
            "test.custom", {"language": "fr"}, expected_version=0
        ),
        app.customize_configuration(
            "test.custom", {"language": "de"}, expected_version=0
        ),
        return_exceptions=True,
    )
    assert sorted(type(r).__name__ for r in results) == [
        "ConfigurationState",
        "VersionConflict",
    ]
    state = await app.configuration("test.custom")
    assert state.version == 1

    prompt_results = await asyncio.gather(
        app.customize_prompt(
            "test.custom", "answer", "Reply in {language}.", expected_version=0
        ),
        app.customize_prompt(
            "test.custom", "answer", "Respond in {language}.", expected_version=0
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(r, VersionConflict) for r in prompt_results) == 1
    assert len(await app.prompt_history("test.custom", "answer")) == 1


async def test_concurrent_changes_without_a_version_are_all_applied(
    app: Brevia,
) -> None:
    await asyncio.gather(
        app.customize_configuration("test.custom", {"language": "fr"}),
        app.customize_configuration("test.custom", {"max_words": 20}),
        app.customize_prompt("test.custom", "answer", "Reply in {language}."),
        app.customize_prompt("test.custom", "answer", "Respond in {language}."),
    )
    state = await app.configuration("test.custom")
    # Changes wait for each other: neither field is lost.
    assert state.customization == {"language": "fr", "max_words": 20}
    assert state.version == 2
    history = await app.prompt_history("test.custom", "answer")
    assert [r.version for r in history] == [2, 1]


async def test_prompt_history_and_reset(app: Brevia) -> None:
    await app.customize_prompt(
        "test.custom", "answer", "Reply in {language}.", author="ed"
    )
    state = await app.reset_prompt("test.custom", "answer")
    assert (state.customization, state.effective, state.version) == (None, PROMPT, 2)
    history = await app.prompt_history("test.custom", "answer")
    assert [(r.version, r.operation, r.author) for r in history] == [
        (2, "reset", None),
        (1, "customize", "ed"),
    ]
    assert history[1].text == "Reply in {language}."


async def test_customised_run_records_snapshot_calls_and_contents(
    app: Brevia, database_url: str, schema: str
) -> None:
    await app.customize_configuration("test.custom", {"language": "fr"})
    await app.customize_prompt("test.custom", "answer", "Reply in {language}.")
    with patch.object(adapter_module, "_resolve_model", return_value=model()):
        await app.run("test.custom", {"text": "Is it stored?"})

    reader = sync_engine(database_url)
    try:
        with reader.connect() as connection:
            connection = connection.execution_options(
                schema_translate_map={SCHEMA: schema}
            )
            (run,) = connection.execute(select(runs)).mappings().all()
            (call,) = connection.execute(select(model_calls)).mappings().all()
            (content,) = connection.execute(select(trace_contents)).mappings().all()
    finally:
        reader.dispose()
    assert run["snapshot"]["config"]["language"] == "fr"
    prompt = run["snapshot"]["prompts"]["answer"]
    assert (prompt["text"], prompt["source"], prompt["version"]) == (
        "Reply in {language}.",
        "database",
        1,
    )
    assert content["call_id"] == call["id"]
    assert content["instructions"] == "Reply in fr."
    assert content["user_text"] == "Is it stored?"
    assert content["output"] == {"answer": "Yes."}
    assert content["deleted_at"] is None
    assert content["expires_at"] == run["finished_at"] + timedelta(days=3)


async def test_contents_without_retention_have_no_expiry(
    database_url: str, schema: str, tmp_path: Path
) -> None:
    project = PROJECT.replace("retention_days = 3", "retention_days = 0")
    async with started(database_url, schema, tmp_path, project) as app:
        with patch.object(adapter_module, "_resolve_model", return_value=model()):
            result = await app.run("test.custom", {"text": "Kept?"})
    assert result == Answer(answer="Yes.")

    reader = sync_engine(database_url)
    try:
        with reader.connect() as connection:
            connection = connection.execution_options(
                schema_translate_map={SCHEMA: schema}
            )
            (run,) = connection.execute(select(runs)).mappings().all()
            (content,) = connection.execute(select(trace_contents)).mappings().all()
    finally:
        reader.dispose()
    assert run["status"] == "succeeded"
    assert content["user_text"] == "Kept?"
    assert content["expires_at"] is None


async def test_each_content_belongs_to_its_call(
    app: Brevia, database_url: str, schema: str
) -> None:
    async def three_calls(request: Question, ctx: RunContext[CustomConfig]) -> Answer:
        model = ctx.model()
        for user_text in ("first", "second"):
            await model.generate(
                instructions="Answer.", user_text=user_text, output_type=Answer
            )
        with contextlib.suppress(OutputInvalid):
            await model.generate(
                instructions="Answer.",
                user_text="third",
                output_type=Answer,
                max_attempts=1,
            )
        return Answer(answer="done")

    app.register_activity(
        name="test.three",
        version="1",
        function=three_calls,
        input_type=Question,
        output_type=Answer,
        config_type=CustomConfig,
        capture="full",
    )

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        text = str(messages[-1])
        value = {"wrong": 1} if "third" in text else {"answer": "ok"}
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, value)],
            usage=RequestUsage(input_tokens=10, output_tokens=2),
        )

    with patch.object(
        adapter_module, "_resolve_model", return_value=FunctionModel(respond)
    ):
        await app.run("test.three", {"text": "x"}, {})

    reader = sync_engine(database_url)
    try:
        with reader.connect() as connection:
            connection = connection.execution_options(
                schema_translate_map={SCHEMA: schema}
            )
            rows = (
                connection.execute(
                    select(model_calls.c.sequence, model_calls.c.error, trace_contents)
                    .join(trace_contents, trace_contents.c.call_id == model_calls.c.id)
                    .order_by(model_calls.c.sequence)
                )
                .mappings()
                .all()
            )
    finally:
        reader.dispose()
    assert [(r["sequence"], r["user_text"]) for r in rows] == [
        (0, "first"),
        (1, "second"),
        (2, "third"),
    ]
    assert [r["output"] for r in rows] == [{"answer": "ok"}, {"answer": "ok"}, None]
    assert rows[2]["error"] == "output_invalid"


async def test_contents_with_nul_are_stored(
    app: Brevia, database_url: str, schema: str
) -> None:
    # A real NUL becomes U+FFFD; the six characters of the escape stay as text.
    escape = "JSON writes NUL as \\u0000."

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                ToolCallPart(info.output_tools[0].name, {"answer": f"a\x00b {escape}"})
            ],
            usage=RequestUsage(input_tokens=10, output_tokens=2),
        )

    with patch.object(
        adapter_module, "_resolve_model", return_value=FunctionModel(respond)
    ):
        result = await app.run("test.custom", {"text": f"page\x00two {escape}"})
    assert result == Answer(answer=f"a\x00b {escape}")

    reader = sync_engine(database_url)
    try:
        with reader.connect() as connection:
            connection = connection.execution_options(
                schema_translate_map={SCHEMA: schema}
            )
            (run,) = connection.execute(select(runs)).mappings().all()
            (content,) = connection.execute(select(trace_contents)).mappings().all()
    finally:
        reader.dispose()
    assert run["input"] == {"text": f"page\ufffdtwo {escape}"}
    assert run["result"] == {"answer": f"a\ufffdb {escape}"}
    assert content["user_text"] == f"page\ufffdtwo {escape}"
    assert content["output"] == {"answer": f"a\ufffdb {escape}"}


def _hold(database_url: str, schema: str, statement: str) -> Connection:
    """Open a transaction that runs ``statement`` and keeps its locks."""
    engine = sync_engine(database_url)
    connection = engine.connect()
    connection.execute(text(statement.format(schema=schema)))
    return connection


async def test_changes_wait_for_a_locked_customisation(
    app: Brevia, database_url: str, schema: str
) -> None:
    await app.customize_configuration("test.custom", {"language": "fr"})
    holder = _hold(
        database_url,
        schema,
        'SELECT * FROM "{schema}".configurations FOR UPDATE',
    )
    try:
        change = asyncio.create_task(
            app.customize_configuration("test.custom", {"max_words": 20})
        )
        await asyncio.sleep(0.5)
        assert not change.done()  # it waits for the lock
    finally:
        holder.commit()
        holder.close()
    state = await change
    assert state.customization == {"language": "fr", "max_words": 20}
    assert state.version == 2


async def test_first_change_waits_for_a_concurrent_first_insert(
    app: Brevia, database_url: str, schema: str
) -> None:
    # Another process is creating the customisation and has not committed yet.
    holder = _hold(
        database_url,
        schema,
        'INSERT INTO "{schema}".configurations (activity, values, version, '
        "updated_at) VALUES ('test.custom', '{{\"language\": \"de\"}}', 1, now())",
    )
    try:
        change = asyncio.create_task(
            app.customize_configuration(
                "test.custom", {"max_words": 20}, expected_version=0
            )
        )
        await asyncio.sleep(0.5)
        assert not change.done()
    finally:
        holder.commit()
        holder.close()
    with pytest.raises(VersionConflict):
        await change
