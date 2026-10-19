"""Shared fixtures: a simulated model, a store in memory and a started project."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from memory_store import MemoryStore
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage
from summary_example import (
    PROJECT,
    PROMPT,
    SummaryConfig,
    SummaryRequest,
    SummaryResult,
    summarize,
)

from brevia import Brevia
from brevia.config.project import load_project
from brevia.models import client
from brevia.models import pydantic_ai as adapter_module
from brevia.models.spec import ModelInfo, Prices
from brevia.runs.activities import Mode

PRICES = Prices(input=Decimal(1), output=Decimal(2), cached_input=Decimal("0.5"))
INFO = ModelInfo(reasoning_levels=frozenset({"low", "high"}), prices=PRICES)


Respond = Callable[[list[ModelMessage], AgentInfo], ModelResponse]


def responder(
    *outputs: dict[str, Any], input_tokens: int = 100, output_tokens: int = 10
) -> Respond:
    """Function that returns ``outputs`` in order, one per model request."""
    pending = list(outputs)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0].name
        return ModelResponse(
            parts=[ToolCallPart(tool, pending.pop(0))],
            usage=RequestUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        )

    return respond


def together(count: int, respond: Respond) -> FunctionModel:
    """Simulated model that answers only when ``count`` requests have arrived, so
    that concurrent calls all start before any of them is counted."""
    arrived = 0
    everyone = asyncio.Event()

    async def wait_for_all(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        nonlocal arrived
        arrived += 1
        if arrived == count:
            everyone.set()
        await asyncio.wait_for(everyone.wait(), 5)
        return respond(messages, info)

    return FunctionModel(wait_for_all)


def answers(*outputs: dict[str, Any]) -> FunctionModel:
    """Simulated model that returns ``outputs`` in order, one per request."""
    return FunctionModel(responder(*outputs))


class Recorder:
    """Simulated model: records instructions and user text of every request and
    answers with ``respond(instructions, user_text)``."""

    def __init__(self, respond: Callable[[str, str], dict[str, Any]]) -> None:
        self.calls: list[tuple[str, str]] = []
        self.retries: list[str] = []
        self._respond = respond

    def model(self) -> FunctionModel:
        def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            request = messages[-1]
            assert isinstance(request, ModelRequest)
            retry = [p for p in request.parts if isinstance(p, RetryPromptPart)]
            if retry:
                self.retries.append(str(retry[0].content))
            user = next(
                p
                for m in messages
                if isinstance(m, ModelRequest)
                for p in m.parts
                if isinstance(p, UserPromptPart)
            )
            instructions = request.instructions or ""
            text = str(user.content)
            self.calls.append((instructions, text))
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        info.output_tools[0].name, self._respond(instructions, text)
                    )
                ]
            )

        return FunctionModel(answer)


@contextmanager
def simulated(model: Model) -> Iterator[None]:
    """Use ``model`` for every generation in the block, whatever the reference."""
    with patch.object(adapter_module, "_resolve_model", return_value=model):
        yield


def project_brevia(
    tmp_path: Path,
    store: MemoryStore,
    modes: tuple[Mode, ...] = ("direct",),
    **options: Any,
) -> Brevia:
    """Brevia on the summary example project in ``tmp_path``, not started."""
    (tmp_path / "brevia.toml").write_text(PROJECT, encoding="utf-8")
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "summary.md").write_text(PROMPT, encoding="utf-8")
    app = Brevia(
        load_project(tmp_path / "brevia.toml"),
        project_dir=tmp_path,
        store=store,
        **options,
    )
    app.register_activity(
        name="document.summarize",
        version="1",
        function=summarize,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=SummaryConfig,
        prompts={"summary": "prompts/summary.md"},
        overridable=["language"],
        modes=modes,
    )
    return app


@pytest.fixture(autouse=True)
def waits() -> Iterator[list[float]]:
    """Waits between retries of provider errors, recorded instead of slept."""
    recorded: list[float] = []

    async def sleep(seconds: float) -> None:
        recorded.append(seconds)

    with patch.object(client, "_sleep", sleep):
        yield recorded


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
async def brevia(tmp_path: Path, store: MemoryStore) -> AsyncIterator[Brevia]:
    async with project_brevia(tmp_path, store) as app:
        yield app
