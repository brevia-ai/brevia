"""Direct runs: the summary example of the specification, end to end."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import pytest
from conftest import responder, simulated
from pydantic import BaseModel, Field, SecretStr
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from summary_example import (
    NoConfig,
    SummaryConfig,
    SummaryRequest,
    SummaryResult,
    summarize,
)

from brevia import (
    Brevia,
    BreviaSettings,
    InternalError,
    InvalidInput,
    NotFound,
    OverrideNotAllowed,
    RunContext,
    RunLimits,
    RunTimeout,
    Unavailable,
    Unsupported,
)

pytestmark = pytest.mark.unit

SECRET = "-".join(["sk", "secret"])
UNUSED_DATABASE = SecretStr("postgresql://brevia@localhost/unused")  # not contacted


async def test_summary_example_runs_end_to_end(brevia: Brevia) -> None:
    seen: list[str] = []
    respond = responder({"summary": "A short summary."})

    def record(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(str(messages[0]))
        return respond(messages, info)

    with simulated(FunctionModel(record)):
        result = await brevia.run(
            "document.summarize", {"text": "The document."}, {"language": "English"}
        )
    assert result == SummaryResult(summary="A short summary.")
    assert "Summarise the document in English." in seen[0]


async def test_override_not_declared_is_refused_before_any_request(
    brevia: Brevia,
) -> None:
    with pytest.raises(OverrideNotAllowed):
        await brevia.run("document.summarize", {"text": "x"}, {"model": "openai:other"})


async def test_invalid_input_and_unknown_activity(brevia: Brevia) -> None:
    with pytest.raises(InvalidInput):
        await brevia.run("document.summarize", {"text": ""})
    with pytest.raises(NotFound):
        await brevia.run("document.translate", {"text": "x"})


async def test_model_not_declared_in_the_project_is_unsupported(
    brevia: Brevia,
) -> None:
    brevia.register_activity(
        name="test.any-model",
        version="1",
        function=summarize,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=SummaryConfig,
        prompts={"summary": "prompts/summary.md"},
        overridable=["model"],
    )
    with pytest.raises(Unsupported):
        await brevia.run("test.any-model", {"text": "x"}, {"model": "openai:other"})


async def test_unexpected_failure_and_wrong_output_are_internal_errors(
    brevia: Brevia, caplog: pytest.LogCaptureFixture
) -> None:
    async def broken(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        # A runtime value, as a dependency would put in its message; source lines
        # appear in the stack frames, runtime values must not.
        raise RuntimeError(" ".join(["token", SECRET, "leaked by a dependency"]))

    async def wrong(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        return SummaryRequest(text="not a result")  # type: ignore[return-value]

    for name, function in (("broken", broken), ("wrong", wrong)):
        brevia.register_activity(
            name=f"test.{name}",
            version="1",
            function=function,
            input_type=SummaryRequest,
            output_type=SummaryResult,
            config_type=NoConfig,
        )
    with caplog.at_level(logging.ERROR), pytest.raises(InternalError):
        await brevia.run("test.broken", {"text": "x"})
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "RuntimeError" in logged
    assert "in broken" in logged  # the stack frames locate the bug
    assert "sk-secret" not in logged
    assert not any(record.exc_info for record in caplog.records)
    with pytest.raises(InternalError):
        await brevia.run("test.wrong", {"text": "x"})


def test_registration_checks_names_paths_and_project_defaults(brevia: Brevia) -> None:
    common: dict[str, Any] = {
        "version": "1",
        "function": summarize,
        "input_type": SummaryRequest,
        "output_type": SummaryResult,
        "config_type": SummaryConfig,
    }
    with pytest.raises(ValueError, match="already registered"):
        brevia.register_activity(name="document.summarize", **common)
    with pytest.raises(ValueError, match="not a valid dotted name"):
        brevia.register_activity(name="Document Summarize", **common)
    with pytest.raises(ValueError, match="not in the configuration"):
        brevia.register_activity(name="other.one", overridable=["tone"], **common)
    with pytest.raises(ValueError, match="not in the configuration"):
        # `model` is a scalar: it has no children to override
        brevia.register_activity(name="other.three", overridable=["model.x"], **common)
    with pytest.raises(Unavailable):  # no default model for this activity
        brevia.register_activity(name="other.two", **common)


async def test_run_deadline_applies_to_work_without_model_calls(
    brevia: Brevia,
) -> None:
    async def slow(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        await asyncio.sleep(1)
        return SummaryResult(summary="too late")

    brevia.register_activity(
        name="test.slow",
        version="1",
        function=slow,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=NoConfig,
        limits=RunLimits(max_seconds=0.05),
    )
    with pytest.raises(RunTimeout):
        await brevia.run("test.slow", {"text": "x"})


async def test_invalid_max_output_tokens_is_refused_before_any_request(
    brevia: Brevia,
) -> None:
    async def zero_tokens(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        result: SummaryResult = await ctx.model().generate(
            instructions="",
            user_text="x",
            output_type=SummaryResult,
            max_output_tokens=0,
        )
        return result

    brevia.register_activity(
        name="test.zero",
        version="1",
        function=zero_tokens,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=SummaryConfig,
    )
    with pytest.raises(InvalidInput):
        await brevia.run("test.zero", {"text": "x"})


class AliasedConfig(BaseModel):
    lang: str = Field("it", alias="language")


async def test_activity_receives_the_resolved_configuration(brevia: Brevia) -> None:
    seen: list[str] = []

    async def record(
        request: SummaryRequest, ctx: RunContext[AliasedConfig]
    ) -> SummaryResult:
        seen.append(ctx.config.lang)
        return SummaryResult(summary="ok")

    brevia.register_activity(
        name="test.aliased",
        version="1",
        function=record,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=AliasedConfig,
    )
    await brevia.run("test.aliased", {"text": "x"})
    assert seen == ["en"]


async def test_cancelled_run_is_logged(
    brevia: Brevia, caplog: pytest.LogCaptureFixture
) -> None:
    started = asyncio.Event()

    async def waits(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        started.set()
        await asyncio.sleep(10)
        return SummaryResult(summary="never")

    brevia.register_activity(
        name="test.waits",
        version="1",
        function=waits,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=NoConfig,
    )
    task = asyncio.create_task(brevia.run("test.waits", {"text": "x"}))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with caplog.at_level(logging.WARNING), pytest.raises(asyncio.CancelledError):
        await task
    assert any(r.getMessage().startswith("Run cancelled") for r in caplog.records)


def test_project_file_accepts_only_supported_providers(tmp_path: Path) -> None:
    (tmp_path / "brevia.toml").write_text('[models."google:gemini"]\n', "utf-8")
    with pytest.raises(Unavailable):
        Brevia.from_settings(
            BreviaSettings(
                project_file=tmp_path / "brevia.toml", database_url=UNUSED_DATABASE
            )
        )


async def test_blocking_work_past_the_deadline_is_detected_on_return(
    brevia: Brevia,
) -> None:
    async def blocks(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        time.sleep(0.1)  # noqa: ASYNC251  (blocks the loop on purpose)
        return SummaryResult(summary="late")

    brevia.register_activity(
        name="test.blocks",
        version="1",
        function=blocks,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=NoConfig,
        limits=RunLimits(max_seconds=0.05),
    )
    with pytest.raises(RunTimeout):
        await brevia.run("test.blocks", {"text": "x"})


def test_registration_refuses_defaults_with_typos_or_undeclared_models(
    brevia: Brevia,
) -> None:
    common: dict[str, Any] = {
        "version": "1",
        "function": summarize,
        "input_type": SummaryRequest,
        "output_type": SummaryResult,
        "config_type": SummaryConfig,
    }
    with pytest.raises(Unavailable, match="unknown fields"):
        brevia.register_activity(name="test.typo", **common)
    with pytest.raises(Unavailable, match="not declared"):
        brevia.register_activity(name="test.undeclared", **common)
