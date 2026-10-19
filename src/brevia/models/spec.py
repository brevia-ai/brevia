"""Model use, declared capabilities and prices.

A :class:`ModelSpec` says which configured model an activity uses and with which
options. A :class:`ModelInfo` declares, in the project file, what that model supports
and what it costs. Options are checked against the declaration before any request:
capabilities are never inferred from the model name.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from brevia.config import defaults
from brevia.errors import Unsupported

ReasoningLevel = Literal["minimal", "low", "medium", "high", "xhigh", "max"]
"""Reasoning effort levels understood by the model adapters."""

PROVIDERS = ("openai", "anthropic", "ollama")
"""Providers supported by the model adapter."""

MODEL_REFERENCE = rf"^({'|'.join(PROVIDERS)}):.+$"
"""Pattern of a model reference: ``provider:name`` with a supported provider."""


class ModelSpec(BaseModel):
    """How an activity uses a model.

    A model reference alone (``"openai:gpt-6-luna"``) is accepted where a
    ``ModelSpec`` is expected and stands for that model with the default options.

    Attributes:
        model: Configured model reference in the form ``provider:name``, for
            example ``openai:gpt-6-luna``, ``anthropic:claude-sonnet-5-5`` or
            ``ollama:llama3.3``.
        reasoning: ``None`` keeps the model default, ``False`` turns reasoning off,
            ``True`` enables the adapter's standard effort (``medium`` for OpenAI),
            or a level selects an explicit effort. Levels are provider-specific:
            equal names do not promise equal reasoning budgets or quality.
        temperature: Sampling temperature; ``None`` keeps the model default.
        max_tokens: Maximum number of tokens that each request may generate;
            ``None`` sends no limit, so a response may reach the maximum of the model.
            For reasoning models it includes the reasoning tokens: a request that
            reaches it may end before any visible answer, and fails at once with
            ``output_invalid`` and ``reason`` ``max_tokens``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(pattern=MODEL_REFERENCE)
    reasoning: ReasoningLevel | bool | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=defaults.MODEL_MAX_TOKENS, ge=1)

    @model_validator(mode="before")
    @classmethod
    def _from_reference(cls, data: Any) -> Any:
        return {"model": data} if isinstance(data, str) else data

    @property
    def reasoning_active(self) -> bool:
        """Whether this use explicitly turns reasoning on."""
        return self.reasoning is not None and self.reasoning is not False


class Prices(BaseModel):
    """Prices in USD per million tokens. Costs computed from them are estimates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input: Decimal = Field(ge=0)
    output: Decimal = Field(ge=0)
    cached_input: Decimal | None = Field(
        default=None, ge=0, description="Price of input tokens read from the cache."
    )
    cache_write: Decimal | None = Field(
        default=None, ge=0, description="Price of input tokens written to the cache."
    )


class ModelInfo(BaseModel):
    """Capabilities and prices of a model, declared in the project file.

    Attributes:
        reasoning_levels: Reasoning levels the model accepts; empty if reasoning
            cannot be controlled.
        temperature: Whether the model accepts a temperature.
        temperature_with_reasoning: Whether a temperature is accepted while
            reasoning is on.
        prices: Prices used to estimate costs; without them the cost is unknown.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    reasoning_levels: frozenset[ReasoningLevel] = frozenset()
    temperature: bool = True
    temperature_with_reasoning: bool = False
    prices: Prices | None = None


def check_capabilities(spec: ModelSpec, info: ModelInfo) -> None:
    """Reject options that the declared capabilities of the model do not allow.

    Raises:
        Unsupported: An option is not supported by the model.
    """
    if spec.reasoning_active and not info.reasoning_levels:
        raise Unsupported(
            f"Reasoning cannot be controlled for {spec.model}",
            {"model": spec.model, "option": "reasoning"},
        )
    if isinstance(spec.reasoning, str) and spec.reasoning not in info.reasoning_levels:
        raise Unsupported(
            f"Reasoning level {spec.reasoning!r} is not declared for {spec.model}",
            {
                "model": spec.model,
                "option": "reasoning",
                "allowed": sorted(info.reasoning_levels),
            },
        )
    if spec.temperature is None:
        return
    if not info.temperature:
        raise Unsupported(
            f"Temperature is not accepted by {spec.model}",
            {"model": spec.model, "option": "temperature"},
        )
    if spec.reasoning_active and not info.temperature_with_reasoning:
        raise Unsupported(
            f"Temperature is not accepted by {spec.model} while reasoning is on",
            {"model": spec.model, "option": "temperature"},
        )
