"""Translate validated Brevia options without silently dropping requested settings."""

from __future__ import annotations

from typing import Any

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.settings import ModelSettings

from brevia.errors import Unsupported
from brevia.models import fake
from brevia.models.spec import ModelSpec


def settings_for(spec: ModelSpec, model: Model, timeout: float | None) -> ModelSettings:
    """Resolve settings, rejecting known adapter substitutions before any request.

    The project capability declaration remains the first check; the installed
    adapter profile is an additional constraint, never a model discovery service.
    """
    profile = model.profile
    reasoning = spec.reasoning
    active = spec.reasoning_active or (
        reasoning is None and profile.get("thinking_enabled_by_default", False)
    )
    settings = ModelSettings()
    _common(settings, spec, timeout)
    if spec.temperature is not None:
        if isinstance(model, AnthropicModel) and model.profile.get(
            "anthropic_disallows_sampling_settings", False
        ):
            _unsupported(spec, "temperature")
        if isinstance(model, OpenAIResponsesModel) and (
            "temperature" in model.profile.get("openai_unsupported_model_settings", ())
            or (model.profile.get("openai_supports_reasoning", False) and active)
        ):
            _unsupported(spec, "temperature")
        settings["temperature"] = spec.temperature
    if isinstance(model, OpenAIResponsesModel):
        if reasoning == "minimal" and not model.profile.get(
            "openai_supports_minimal_reasoning_effort", True
        ):
            _unsupported(spec, "reasoning")
        # OpenAI does not store the responses for later retrieval: the reasoning of a
        # call is sent back encrypted by the adapter, so tool turns work without stored
        # state.
        openai = OpenAIResponsesModelSettings(openai_store=False)
        _common(openai, spec, timeout)
        if "temperature" in settings:
            openai["temperature"] = settings["temperature"]
        if reasoning is not None:
            effort = (
                "medium"
                if reasoning is True
                else "none"
                if reasoning is False
                else reasoning
            )
            openai["openai_reasoning_effort"] = effort
        return openai
    if reasoning == "max":
        # The unified setting has no max: Anthropic takes it as an effort, the other
        # adapters cannot apply it. Never approximate it as a lower level. A fake does
        # not check the declared reasoning, so the level is left to the declaration.
        if model is fake.installed():
            return settings
        if not (
            isinstance(model, AnthropicModel)
            and model.profile.get("anthropic_supports_effort", False)
        ):
            _unsupported(spec, "reasoning")
        anthropic = AnthropicModelSettings(anthropic_effort="max")
        _common(anthropic, spec, timeout)
        if "temperature" in settings:
            anthropic["temperature"] = settings["temperature"]
        return anthropic
    elif reasoning is not None:
        if (
            isinstance(model, AnthropicModel)
            and model.profile.get("anthropic_supports_effort", False)
            and (
                reasoning == "minimal"
                or (
                    reasoning == "xhigh"
                    and not model.profile.get("anthropic_supports_xhigh_effort", False)
                )
            )
        ):
            _unsupported(spec, "reasoning")
        settings["thinking"] = reasoning
    return settings


def _common(settings: ModelSettings, spec: ModelSpec, timeout: float | None) -> None:
    """Set the output limit and the timeout, when they have a value.

    Without a value nothing is sent: the provider applies the maximum of the model
    (Pydantic AI fills it in for Anthropic, whose API requires it).
    """
    if spec.max_tokens is not None:
        settings["max_tokens"] = spec.max_tokens
    if timeout is not None:
        settings["timeout"] = timeout


def effective_options(settings: ModelSettings) -> dict[str, Any]:
    """Known applied options, with provider-independent names where meaningful."""
    result: dict[str, Any] = {}
    for source, target in (
        ("max_tokens", "max_tokens"),
        ("temperature", "temperature"),
        ("thinking", "reasoning"),
        ("openai_reasoning_effort", "reasoning"),
        ("anthropic_effort", "reasoning"),
        ("openai_store", "store"),
    ):
        if source in settings:
            result[target] = settings[source]  # type: ignore[literal-required]
    return result


def _unsupported(spec: ModelSpec, option: str) -> None:
    raise Unsupported(
        f"The adapter cannot apply {option} as requested for {spec.model}",
        {"model": spec.model, "option": option},
    )
