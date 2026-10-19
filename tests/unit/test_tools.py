"""Tools called by a fake model during a generation: read_file, save_file and a tool
of the project."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from conftest import simulated
from memory_store import MemoryStore
from pydantic import BaseModel
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from brevia import (
    Brevia,
    FileSource,
    FileStore,
    InvalidInput,
    LimitExceeded,
    NotFound,
    RunContext,
    RunLimits,
    Unavailable,
)
from brevia.config.project import load_project
from brevia.tools import Tool, ToolRetry, read_file, save_file

pytestmark = pytest.mark.unit

MODEL = "openai:test-model"
PROJECT = f"""
[models."{MODEL}"]

[activities."test.tools"]
model = "{MODEL}"

[activities."test.retry"]
model = "{MODEL}"
"""


class Config(BaseModel):
    model: str


class Request(BaseModel):
    files: list[FileSource] = []
    tools: list[str]


class Answer(BaseModel):
    answer: str


async def shout(ctx: RunContext[Any], text: str) -> str:
    """A tool of the project."""
    if text == "fail":
        raise Unavailable("Service down")
    return text.upper()


SHOUT = Tool(name="shout", description="Upper case of a text.", function=shout)


async def with_tools(request: Request, ctx: RunContext[Config]) -> Answer:
    available = {
        "read_file": lambda: read_file(*request.files, max_chars=12),
        "save_file": lambda: save_file,
        "shout": lambda: SHOUT,
    }
    answer: Answer = await ctx.model().generate(
        instructions="Use the tools.",
        user_text="Go.",
        output_type=Answer,
        tools=[available[name]() for name in request.tools],
    )
    return answer


class Script:
    """Fake model: calls the tools in ``steps``, one per request, then answers with
    every tool result it received; records the tools it was offered."""

    def __init__(self, *steps: tuple[str, dict[str, Any]]) -> None:
        self.steps = list(steps)
        self.offered: list[str] = []
        self.returns: list[Any] = []
        self.retries: list[str] = []

    def model(self) -> FunctionModel:
        def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            self.offered = [tool.name for tool in info.function_tools]
            request = messages[-1]
            assert isinstance(request, ModelRequest)
            for part in request.parts:
                if isinstance(part, ToolReturnPart):
                    self.returns.append(
                        part.content.model_dump()
                        if isinstance(part.content, BaseModel)
                        else part.content
                    )
                if isinstance(part, RetryPromptPart):
                    self.retries.append(str(part.content))
            if self.steps:
                name, arguments = self.steps.pop(0)
                return ModelResponse(parts=[ToolCallPart(name, arguments)])
            text = json.dumps(self.returns, default=str)
            return ModelResponse(
                parts=[ToolCallPart(info.output_tools[0].name, {"answer": text})]
            )

        return FunctionModel(answer)


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
async def app(tmp_path: Path, store: MemoryStore) -> AsyncIterator[Brevia]:
    (tmp_path / "brevia.toml").write_text(PROJECT, encoding="utf-8")
    brevia = Brevia(
        load_project(tmp_path / "brevia.toml"),
        project_dir=tmp_path,
        store=store,
        files=FileStore(tmp_path / "files"),
    )
    brevia.register_activity(
        name="test.tools",
        version="1",
        function=with_tools,
        input_type=Request,
        output_type=Answer,
        config_type=Config,
        limits=RunLimits(max_tool_calls=3),
    )
    async with brevia:
        yield brevia


@pytest.fixture
def notes(tmp_path: Path) -> FileSource:
    path = tmp_path / "notes.md"
    path.write_text("first part\n\nsecond part of the notes", encoding="utf-8")
    return FileSource(name="notes.md", path=path)


async def test_read_file_returns_sections_from_start_within_the_size(
    app: Brevia, notes: FileSource
) -> None:
    script = Script(
        ("read_file", {"name": "notes.md"}),
    )
    with simulated(script.model()):
        await app.run("test.tools", Request(files=[notes], tools=["read_file"]))

    assert script.offered == ["read_file"]
    [first] = script.returns
    assert first["sections"] == [
        {"title": None, "page": None, "text": "first part\n\n"}
    ]
    assert first["truncated"] is True
    assert first["next_start"] == 0
    assert first["next_offset"] == 12
    assert first["total"] == 1


async def test_a_wrong_file_name_goes_back_to_the_model(
    app: Brevia, notes: FileSource
) -> None:
    script = Script(
        ("read_file", {"name": "other.md"}),
        ("read_file", {"name": "notes.md", "start": 5}),
    )
    with simulated(script.model()):
        await app.run("test.tools", Request(files=[notes], tools=["read_file"]))

    assert len(script.retries) == 2
    assert "Unknown file 'other.md'" in script.retries[0]
    assert "start must be between 0 and 0" in script.retries[1]


async def test_save_file_saves_an_output_of_the_run(app: Brevia) -> None:
    script = Script(("save_file", {"name": "notes.md", "text": "Saved."}))
    run_id = str(uuid.uuid4())
    with simulated(script.model()):
        await app.run("test.tools", Request(tools=["save_file"]), run_id=run_id)

    [saved] = script.returns
    assert saved["name"] == "notes.md"
    assert saved["size"] == 6
    assert app.files is not None
    assert app.files.output_path(run_id, "notes.md").read_text() == "Saved."


async def test_a_tool_of_the_project_and_its_log(
    app: Brevia, caplog: pytest.LogCaptureFixture
) -> None:
    script = Script(("shout", {"text": "hello"}))
    with simulated(script.model()), caplog.at_level(logging.INFO):
        result = await app.run("test.tools", Request(tools=["shout"]))

    assert result == Answer(answer='["HELLO"]')
    assert any(
        record.getMessage().startswith("Tool shout: ok in") for record in caplog.records
    )


async def test_an_error_that_the_model_cannot_correct_stops_the_run(
    app: Brevia,
) -> None:
    script = Script(("shout", {"text": "fail"}))
    with simulated(script.model()), pytest.raises(Unavailable):
        await app.run("test.tools", Request(tools=["shout"]))


async def test_tool_calls_count_against_the_limit_of_the_run(app: Brevia) -> None:
    script = Script(*[("shout", {"text": str(n)}) for n in range(5)])
    with simulated(script.model()), pytest.raises(LimitExceeded):
        await app.run("test.tools", Request(tools=["shout"]))


async def test_the_tools_offered_are_recorded_with_the_call(
    app: Brevia, store: MemoryStore
) -> None:
    run_id = uuid.uuid4()
    script = Script(("shout", {"text": "a"}))
    with simulated(script.model()):
        await app.run("test.tools", Request(tools=["shout"]), run_id=str(run_id))

    [call] = store.calls_of(run_id)
    assert call.options["tools"] == ["shout"]
    assert call.tool_calls == 1


def test_read_file_needs_distinct_sources(notes: FileSource) -> None:
    with pytest.raises(ValueError, match="at least one"):
        read_file()
    with pytest.raises(ValueError, match="different names"):
        read_file(notes, notes)


async def test_tools_need_a_model_of_the_run() -> None:
    from brevia.models import ModelClient
    from brevia.models.limits import LimitTracker
    from brevia.models.spec import ModelInfo, ModelSpec

    client = ModelClient(ModelSpec(model=MODEL), ModelInfo(), LimitTracker(RunLimits()))
    with pytest.raises(ValueError, match=r"ctx\.model"):
        await client.generate(
            instructions="", user_text="", output_type=Answer, tools=[SHOUT]
        )


async def test_pages_keep_every_character_of_a_long_section(
    app: Brevia, notes: FileSource
) -> None:
    script = Script(
        ("read_file", {"name": "notes.md"}),
        ("read_file", {"name": "notes.md", "start": 0, "offset": 12}),
        ("read_file", {"name": "notes.md", "start": 0, "offset": 24}),
    )
    with simulated(script.model()):
        await app.run("test.tools", Request(files=[notes], tools=["read_file"]))
    assert "".join(page["sections"][0]["text"] for page in script.returns) == (
        "first part\n\nsecond part of the notes"
    )
    assert script.returns[-1]["next_start"] is None
    assert script.returns[-1]["truncated"] is False


async def test_tool_input_validation_can_be_corrected(app: Brevia) -> None:
    script = Script(("shout", {"text": 123}), ("shout", {"text": "fixed"}))
    with simulated(script.model()):
        await app.run("test.tools", Request(tools=["shout"]))
    assert len(script.retries) == 1
    assert script.returns == ["FIXED"]


async def test_reusing_a_reader_does_not_reuse_another_runs_document(
    notes: FileSource,
) -> None:
    from unittest.mock import AsyncMock

    from brevia import Document
    from brevia.tools import FileText

    reader = read_file(notes)
    contexts = [
        RunContext(
            run_id=str(uuid.uuid4()),
            config=Config(model=MODEL),
            snapshot={
                "activity": {"name": "test"},
                "prompts": {},
                "models": {},
                "model_overrides": {},
                "capture": {"mode": "metadata", "retention_days": 1},
                "limits": {},
            },
        )
        for _ in range(2)
    ]
    for ctx, text in zip(contexts, ("first", "second"), strict=True):
        ctx.files.read = AsyncMock(return_value=Document.from_text(text))  # type: ignore[method-assign]
        result = await reader.function(ctx, "notes.md")
        assert isinstance(result, FileText)
        assert result.sections[0].text == text


async def test_duplicate_tool_names_are_refused() -> None:
    from brevia.models import ModelClient
    from brevia.models.limits import LimitTracker
    from brevia.models.spec import ModelInfo, ModelSpec

    client = ModelClient(ModelSpec(model=MODEL), ModelInfo(), LimitTracker(RunLimits()))
    with pytest.raises(ValueError, match="different"):
        await client.generate(
            instructions="", user_text="", output_type=Answer, tools=[SHOUT, SHOUT]
        )


def test_invalid_tool_name_is_refused() -> None:
    with pytest.raises(ValueError, match="name"):
        Tool(name="not a tool", description="Bad", function=shout)


@pytest.mark.parametrize(
    ("content", "error"),
    [(b"not a PDF: private text", InvalidInput), (None, NotFound)],
)
async def test_a_file_that_cannot_be_read_stops_the_run(
    app: Brevia, tmp_path: Path, content: bytes | None, error: type[Exception]
) -> None:
    # A damaged file and a missing input are not arguments the model can correct:
    # the run stops with their error at the first call, without retries.
    path = tmp_path / "report.pdf"
    if content is not None:
        path.write_bytes(content)
    script = Script(*[("read_file", {"name": "report.pdf"})] * 3)
    source = FileSource(name="report.pdf", path=path)
    with simulated(script.model()), pytest.raises(error):
        await app.run("test.tools", Request(files=[source], tools=["read_file"]))

    assert script.retries == []
    assert len(script.steps) == 2


async def test_a_wrong_name_for_save_file_goes_back_to_the_model(app: Brevia) -> None:
    script = Script(
        ("save_file", {"name": "../outside.md", "text": "x"}),
        ("save_file", {"name": "notes.md", "text": "x"}),
    )
    with simulated(script.model()):
        await app.run("test.tools", Request(tools=["save_file"]))

    assert len(script.retries) == 1
    assert "Not a valid file name" in script.retries[0]
    [saved] = script.returns
    assert saved["name"] == "notes.md"


async def test_a_tool_of_the_project_asks_for_a_correction_with_tool_retry(
    app: Brevia,
) -> None:
    async def positive(ctx: RunContext[Any], number: int) -> int:
        if number < 0:
            raise ToolRetry("number must not be negative")
        return number

    tool = Tool(name="positive", description="A positive number.", function=positive)
    calls = [("positive", {"number": -1}), ("positive", {"number": 2})]
    script = Script(*calls)

    async def run(request: Request, ctx: RunContext[Config]) -> Answer:
        answer: Answer = await ctx.model().generate(
            instructions="", user_text="", output_type=Answer, tools=[tool]
        )
        return answer

    app.register_activity(
        name="test.retry",
        version="1",
        function=run,
        input_type=Request,
        output_type=Answer,
        config_type=Config,
    )
    with simulated(script.model()):
        await app.run("test.retry", Request(tools=[]))

    assert script.retries == ["number must not be negative"]
    assert script.returns == [2]


def test_arguments_of_a_tool_must_be_named_parameters() -> None:
    async def positional(ctx: RunContext[Any], text: str, /) -> str:
        return text

    async def variadic(ctx: RunContext[Any], *texts: str) -> str:
        return "".join(texts)

    for function in (positional, variadic):
        with pytest.raises(ValueError, match="named parameters"):
            Tool(name="bad", description="Bad", function=function)
