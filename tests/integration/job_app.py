"""Application run by the worker processes of the integration tests.

``brevia worker integration.job_app:build`` imports it from ``tests``. The model is
simulated, once the application is built, and logs every request to ``JOB_CALL_LOG``,
so that tests count requests across processes. ``JOB_CRASH_AT`` kills the process once
at a named point, recorded in the file ``JOB_CRASH_MARKER``:

- ``between-calls``: after the first model call of ``test.two_calls``;
- ``in-second-call``: while the model answers the second call, before the worker
  receives the answer.

``JOB_HOLD_SECONDS`` makes ``test.two_calls`` wait that long between its calls, and
``JOB_MAX_SECONDS`` sets its maximum duration.
"""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from brevia import Brevia, RunContext, RunLimits
from brevia.models import pydantic_ai as adapter_module

MODEL = "openai:test-model"
PROJECT = f"""
[traces]
retention_days = 30

[models."{MODEL}"]
prices = {{ input = 1, output = 2 }}

[activities."test.two_calls"]
model = "{MODEL}"
"""


class Question(BaseModel):
    text: str


class Answers(BaseModel):
    first: str
    second: str
    language: str


class Answer(BaseModel):
    answer: str


class TwoCallsConfig(BaseModel):
    model: str
    language: str = "it"


def crash_at(point: str) -> None:
    """Kill this process at ``point`` once, when the test asks for it."""
    marker = os.environ.get("JOB_CRASH_MARKER")
    if os.environ.get("JOB_CRASH_AT") != point or not marker:
        return
    if Path(marker).exists():
        return
    Path(marker).write_text(point, encoding="utf-8")
    os.kill(os.getpid(), signal.SIGKILL)


def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    text = " ".join(
        str(part.content)
        for part in messages[-1].parts
        if part.part_kind == "user-prompt"
    )
    log = os.environ.get("JOB_CALL_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as file:
            file.write(f"{os.getpid()} {text}\n")
    if text.startswith("second"):
        crash_at("in-second-call")
    value: dict[str, Any] = {"answer": f"answer to {text}"}
    return ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, value)],
        usage=RequestUsage(input_tokens=10, output_tokens=2),
    )


async def two_calls(request: Question, ctx: RunContext[TwoCallsConfig]) -> Answers:
    model = ctx.model()
    first = await model.generate(
        instructions="Answer.",
        user_text=f"first {request.text}",
        output_type=Answer,
    )
    crash_at("between-calls")
    await asyncio.sleep(float(os.environ.get("JOB_HOLD_SECONDS") or 0))
    second = await model.generate(
        instructions="Answer.", user_text=f"second {request.text}", output_type=Answer
    )
    return Answers(
        first=first.answer, second=second.answer, language=ctx.config.language
    )


def build() -> Brevia:
    """The application, from the settings of the environment, with the simulated
    model in this process."""
    adapter_module._resolve_model = lambda reference: FunctionModel(_respond)
    path = Path(os.environ["BREVIA_PROJECT_FILE"])
    if not path.exists():
        path.write_text(PROJECT, encoding="utf-8")
    brevia = Brevia.from_settings()
    brevia.register_activity(
        name="test.two_calls",
        version="1",
        function=two_calls,
        input_type=Question,
        output_type=Answers,
        config_type=TwoCallsConfig,
        customizable=["language"],
        modes=("job",),
        capture="full",
        limits=RunLimits(max_seconds=float(os.environ.get("JOB_MAX_SECONDS") or 900)),
    )
    return brevia
