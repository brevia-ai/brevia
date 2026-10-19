"""Fake models: answers without a model provider, for tests and local runs.

While a fake is installed, every model call of the process uses it instead of the
declared model: no provider is called, no credentials are needed and nothing is paid.
Runs record ``fake`` as their model adapter, so that their records cannot be taken for
real ones. A fake is installed by ``BREVIA_FAKE_MODELS`` (see
:meth:`brevia.Brevia.from_settings`) or by :func:`brevia.testing.fake_model`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib.metadata import version
from typing import Any

from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RequestUsage

ADAPTER = {"name": "fake", "version": version("brevia")}
"""Model adapter recorded by runs that use a fake model."""

INPUT_TOKENS = 100
OUTPUT_TOKENS = 20
"""Usage reported by each request of a scripted fake."""

_default: Model | None = None
"""Fake of the process, from ``BREVIA_FAKE_MODELS``."""

_override: Model | None = None
"""Fake of a :func:`brevia.testing.fake_model` block; it prevails over the default."""


def install_default(model: Model | None) -> None:
    """Use ``model`` for every model call of the process; ``None`` removes it."""
    global _default
    _default = model


def install(model: Model | None) -> None:
    """Use ``model`` instead of the default fake, if any; ``None`` removes it."""
    global _override
    _override = model


def overriding() -> Model | None:
    """The fake of the current block, if any."""
    return _override


def installed() -> Model | None:
    """The fake in use, if any: that of the current block, or that of the process."""
    return _override if _override is not None else _default


def from_schema() -> Model:
    """A fake that answers with an output generated from the output schema."""
    return TestModel()


def scripted(outputs: Sequence[BaseModel | Mapping[str, Any]]) -> Model:
    """A fake that answers with ``outputs`` in order, one per request; the last one
    is repeated when more requests are made."""
    if not outputs:
        raise ValueError("A scripted fake needs at least one output")
    answers = [
        o.model_dump(mode="json") if isinstance(o, BaseModel) else dict(o)
        for o in outputs
    ]
    sent = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal sent
        answer = answers[min(sent, len(answers) - 1)]
        sent += 1
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, answer)],
            usage=RequestUsage(input_tokens=INPUT_TOKENS, output_tokens=OUTPUT_TOKENS),
        )

    return FunctionModel(respond)
