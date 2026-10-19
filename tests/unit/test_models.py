"""Model use: declared capabilities, cost estimates, generation, limits and errors."""

from __future__ import annotations

import asyncio
import gc
import time
import traceback
import weakref
from decimal import Decimal
from typing import Any, assert_type
from unittest.mock import patch

import pytest
from conftest import INFO, PRICES, answers, responder, simulated, together
from pydantic import BaseModel, ValidationError
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RunUsage
from summary_example import MODEL

from brevia.errors import (
    LimitExceeded,
    OutputInvalid,
    ProviderError,
    RunTimeout,
    Unavailable,
    Unsupported,
)
from brevia.models import client as client_module
from brevia.models import providers
from brevia.models.client import ModelClient, estimate_cost
from brevia.models.limits import LimitTracker, RunLimits
from brevia.models.pydantic_ai import _output_function, _resolve_model
from brevia.models.spec import ModelInfo, ModelSpec, check_capabilities

pytestmark = pytest.mark.unit


class Summary(BaseModel):
    summary: str


def no_digits(output: Summary) -> list[str]:
    return ["no digits allowed"] if any(c.isdigit() for c in output.summary) else []


def tracker(limits: RunLimits | None = None) -> LimitTracker:
    return LimitTracker(limits or RunLimits())


def client(limits: RunLimits | None = None, info: ModelInfo = INFO) -> ModelClient:
    return ModelClient(
        ModelSpec(model=MODEL), info, LimitTracker(limits or RunLimits())
    )


# ---------- capabilities ----------


@pytest.mark.parametrize(
    ("options", "info"),
    [
        ({"reasoning": "low"}, ModelInfo()),
        ({"reasoning": "xhigh"}, INFO),
        ({"temperature": 0.3}, ModelInfo(temperature=False)),
        ({"reasoning": "low", "temperature": 0.3}, INFO),
    ],
)
def test_options_outside_declared_capabilities_are_refused(
    options: dict[str, Any], info: ModelInfo
) -> None:
    with pytest.raises(Unsupported):
        check_capabilities(ModelSpec(model=MODEL, **options), info)


def test_declared_options_are_accepted_whatever_the_model_name() -> None:
    info = ModelInfo(
        reasoning_levels=frozenset({"high"}), temperature_with_reasoning=True
    )
    check_capabilities(
        ModelSpec(model="ollama:local", reasoning="high", temperature=0), info
    )
    check_capabilities(ModelSpec(model=MODEL, reasoning=False, temperature=0.3), INFO)


# ---------- cost ----------


def test_cost_prices_cache_reads_separately() -> None:
    usage = RunUsage(input_tokens=1000, cache_read_tokens=400, output_tokens=100)
    # 600 * 1 + 400 * 0.5 + 100 * 2 = 1000 per million tokens
    assert estimate_cost(usage, PRICES) == Decimal("0.001")


def test_cost_is_unknown_without_a_needed_price() -> None:
    assert estimate_cost(RunUsage(input_tokens=10), None) is None
    assert (
        estimate_cost(RunUsage(input_tokens=10, cache_write_tokens=5), PRICES) is None
    )


# ---------- generation ----------


async def test_validator_problems_are_sent_back_and_every_attempt_is_counted() -> None:
    model = client()
    with simulated(answers({"summary": "2 facts"}, {"summary": "two facts"})):
        output = await model.generate(
            instructions="Summarise.",
            user_text="text",
            output_type=Summary,
            validator=no_digits,
        )
    assert output == Summary(summary="two facts")
    usage = model._tracker.usage
    assert (usage.requests, usage.input_tokens, usage.output_tokens) == (2, 200, 20)


async def test_output_still_invalid_after_the_attempts_is_an_error_with_usage() -> None:
    model = client()
    with (
        simulated(answers({"summary": "1"}, {"summary": "2"})),
        pytest.raises(OutputInvalid) as caught,
    ):
        await model.generate(
            instructions="",
            user_text="x",
            output_type=Summary,
            validator=no_digits,
            max_attempts=2,
        )
    assert caught.value.details["last_problems"] == ["no digits allowed"]
    assert model._tracker.usage.requests == 2
    assert model._tracker.usage.calls[0].error == "output_invalid"


async def test_request_limit_of_the_run_stops_the_retries() -> None:
    model = client(RunLimits(max_requests=1))
    with (
        simulated(answers({"summary": "1"}, {"summary": "ok"})),
        pytest.raises(LimitExceeded),
    ):
        await model.generate(
            instructions="", user_text="x", output_type=Summary, validator=no_digits
        )
    assert model._tracker.usage.requests == 1
    with pytest.raises(LimitExceeded):  # no budget left for another call
        await model.generate(instructions="", user_text="x", output_type=Summary)


async def test_deadline_passed_during_a_call_is_a_run_timeout() -> None:
    def slow(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        time.sleep(0.05)
        return responder({"summary": "late"})(messages, info)

    model = client(RunLimits(max_seconds=0.02))
    with simulated(FunctionModel(slow)), pytest.raises(RunTimeout):
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert model._tracker.usage.requests == 1


async def test_provider_error_does_not_expose_the_response_body() -> None:
    def failing(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(503, MODEL, body={"echo": "user document text"})

    model = client()
    with simulated(FunctionModel(failing)), pytest.raises(ProviderError) as caught:
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert caught.value.details["status_code"] == 503
    assert caught.value.details["cause"][0] == "ModelHTTPError"
    assert "echo" not in str(caught.value.to_dict())
    assert "user document" not in caught.value.message
    # Nor does a standard traceback, as logging.exception() would print it.
    assert "user document" not in "".join(traceback.format_exception(caught.value))


async def test_provider_error_names_the_chain_of_causes_without_messages() -> None:
    def failing(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        try:
            raise ConnectionError("header contains sk-secret")
        except ConnectionError as low:
            raise ModelAPIError(MODEL, "Connection error.") from low

    model = client()
    with simulated(FunctionModel(failing)), pytest.raises(ProviderError) as caught:
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert caught.value.details["cause"][:2] == ["ModelAPIError", "ConnectionError"]
    assert "sk-secret" not in str(caught.value.to_dict())
    # The provider exception is not chained: its message may contain request data.
    assert caught.value.__cause__ is None
    assert "sk-secret" not in "".join(traceback.format_exception(caught.value))


async def test_generation_returns_the_requested_type() -> None:
    model = client()
    with simulated(answers({"summary": "ok"})):
        result = await model.generate(
            instructions="", user_text="x", output_type=Summary
        )
    assert_type(result, Summary)  # checked by mypy
    assert result == Summary(summary="ok")


async def test_unknown_price_makes_the_run_cost_unknown() -> None:
    model = client(info=ModelInfo())
    with simulated(answers({"summary": "ok"})):
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert model._tracker.usage.as_dict()["cost_usd"] is None
    assert model._tracker.usage.as_dict()["cost_kind"] == "unknown"


# ---------- provider resolution and error mapping ----------


async def test_missing_provider_configuration_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    model = ModelClient(ModelSpec(model="ollama:llama3.3"), ModelInfo(), tracker())
    with pytest.raises(Unavailable) as caught:
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert caught.value.details["cause"][0] == "UserError"
    assert model._tracker.usage.requests == 0


def test_only_supported_providers_are_accepted() -> None:
    with pytest.raises(ValidationError):
        ModelSpec(model="google:gemini")


async def test_reasoning_cannot_be_turned_off_on_a_model_that_always_reasons() -> None:
    always = FunctionModel(
        responder({"summary": "ok"}), profile={"thinking_always_enabled": True}
    )
    model = ModelClient(ModelSpec(model=MODEL, reasoning=False), INFO, tracker())
    with simulated(always), pytest.raises(Unsupported) as caught:
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert caught.value.details == {"model": MODEL, "option": "reasoning"}
    assert model._tracker.usage.requests == 0
    default = ModelClient(ModelSpec(model=MODEL), INFO, tracker())
    with simulated(always):  # without the option, the model reasons as it always does
        await default.generate(instructions="", user_text="x", output_type=Summary)


async def test_reasoning_that_the_adapter_would_drop_is_refused() -> None:
    no_thinking = FunctionModel(responder({"summary": "ok"}))
    model = ModelClient(ModelSpec(model=MODEL, reasoning="low"), INFO, tracker())
    with simulated(no_thinking), pytest.raises(Unsupported):
        await model.generate(instructions="", user_text="x", output_type=Summary)
    thinking = FunctionModel(
        responder({"summary": "ok"}), profile={"supports_thinking": True}
    )
    with simulated(thinking):
        await model.generate(instructions="", user_text="x", output_type=Summary)


@pytest.mark.parametrize(
    ("status", "retryable"), [(400, False), (429, True), (503, True)]
)
async def test_provider_error_is_retryable_only_when_temporary(
    status: int, retryable: bool
) -> None:
    def failing(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status, MODEL)

    with simulated(FunctionModel(failing)), pytest.raises(ProviderError) as caught:
        await client().generate(instructions="", user_text="x", output_type=Summary)
    assert caught.value.retryable is retryable
    assert caught.value.to_dict()["retryable"] is retryable


async def test_truncated_response_is_not_reported_as_exhausted_attempts() -> None:
    def truncated(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[], finish_reason="length")

    model = client()
    with simulated(FunctionModel(truncated)), pytest.raises(OutputInvalid) as caught:
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert caught.value.details == {"reason": "max_tokens"}
    assert "truncated" in caught.value.message
    # Not attempted again: the adapter stops at a truncated response.
    assert model._tracker.usage.requests == 1


async def test_last_problems_describe_a_schema_failure_without_input_values() -> None:
    model = client()
    replies = answers({"summary": "1"}, {"wrong": "SECRET VALUE"})
    with simulated(replies), pytest.raises(OutputInvalid) as caught:
        await model.generate(
            instructions="",
            user_text="x",
            output_type=Summary,
            validator=no_digits,
            max_attempts=2,
        )
    problems = caught.value.details["last_problems"]
    assert problems
    assert all("SECRET" not in problem for problem in problems)
    assert "no digits allowed" not in problems  # not the stale validator problem


def test_output_description_is_not_taken_from_built_in_types() -> None:
    assert _output_function(list[str]).__doc__ is None
    assert _output_function(Summary).__doc__ is None  # no docstring of its own


async def test_concurrent_calls_cannot_spend_the_same_request_budget() -> None:
    model = client(RunLimits(max_requests=1))
    with simulated(answers({"summary": "a"}, {"summary": "b"})):
        results = await asyncio.gather(
            model.generate(instructions="", user_text="x", output_type=Summary),
            model.generate(instructions="", user_text="y", output_type=Summary),
            return_exceptions=True,
        )
    assert sum(isinstance(r, LimitExceeded) for r in results) == 1
    assert model._tracker.usage.requests == 1


async def test_concurrent_calls_going_over_the_token_limit_fail() -> None:
    reply = responder(
        {"summary": "a"}, {"summary": "b"}, input_tokens=30, output_tokens=30
    )

    model = client(RunLimits(max_total_tokens=100))
    with simulated(together(2, reply)):  # both start before either is counted
        results = await asyncio.gather(
            model.generate(instructions="", user_text="x", output_type=Summary),
            model.generate(instructions="", user_text="y", output_type=Summary),
            return_exceptions=True,
        )
    # Each call started with 100 tokens left; the second to finish goes over.
    assert model._tracker.usage.total_tokens == 120
    assert sum(isinstance(r, LimitExceeded) for r in results) == 1


async def test_single_call_over_the_tokens_keeps_its_own_error() -> None:
    reply = responder({"summary": "a"}, input_tokens=30, output_tokens=30)
    model = client(RunLimits(max_total_tokens=50))
    with simulated(FunctionModel(reply)), pytest.raises(LimitExceeded) as caught:
        await model.generate(instructions="", user_text="x", output_type=Summary)
    # Raised by the adapter during the call, with the budget the call had.
    assert caught.value.details["budget"]["tokens"] == 50


async def test_usage_exactly_at_the_token_limit_is_accepted() -> None:
    reply = responder({"summary": "a"}, input_tokens=30, output_tokens=30)
    model = client(RunLimits(max_total_tokens=60))
    with simulated(FunctionModel(reply)):
        result = await model.generate(
            instructions="", user_text="x", output_type=Summary
        )
    assert result == Summary(summary="a")


def test_totals_over_the_limits_are_detected() -> None:
    limits = tracker(RunLimits(max_total_tokens=100, max_tool_calls=2))
    limits.check_totals()
    limits.usage.tool_calls = 2
    limits.check_totals()  # exactly at the limit is accepted
    limits.usage.tool_calls = 3
    with pytest.raises(LimitExceeded) as caught:
        limits.check_totals()
    assert caught.value.details["usage"]["tool_calls"] == 3


async def test_cancelled_call_counts_its_requests_and_frees_its_reservation() -> None:
    async def slow(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(1)
        return responder({"summary": "late"})(messages, info)

    model = client(RunLimits(max_requests=3))
    with simulated(FunctionModel(slow)), pytest.raises(TimeoutError):
        await asyncio.wait_for(
            model.generate(instructions="", user_text="x", output_type=Summary), 0.05
        )
    usage = model._tracker.usage
    assert usage.calls[-1].error == "cancelled"
    # Recorded on every path; without a value, no limit was sent.
    assert usage.calls[-1].options["max_tokens"] is None
    # An in-flight request may have been billed even without a response. Its
    # reservation is released, but the attempt remains spent against the limit.
    assert usage.requests == 1
    assert usage.calls[-1].request_records[0].status == "cancelled"
    assert usage.calls[-1].cost_usd is None
    assert model._tracker.reserve(3).requests == 2


def test_built_in_types_give_no_output_description() -> None:
    assert _output_function(str).__doc__ is None


# ---------- retries of temporary provider errors ----------


def failing_then(
    *statuses: int, headers: dict[str, str] | None = None
) -> FunctionModel:
    """Model that fails with ``statuses`` in order, then answers."""
    pending = list(statuses)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if pending:
            raise ModelHTTPError(pending.pop(0), MODEL, headers=headers)
        return responder({"summary": "ok"})(messages, info)

    return FunctionModel(respond)


async def test_temporary_provider_errors_are_retried_with_growing_waits(
    waits: list[float],
) -> None:
    model = client()
    with simulated(failing_then(503, 429)):
        result = await model.generate(
            instructions="", user_text="x", output_type=Summary
        )
    assert result == Summary(summary="ok")
    assert len(waits) == 2
    assert 0.5 <= waits[0] <= 1
    assert 1 <= waits[1] <= 2
    # Each failed request counts as a request of the run.
    assert model._tracker.usage.requests == 3
    (call,) = model._tracker.usage.calls
    assert call.requests == 3
    assert call.error is None


async def test_the_wait_asked_by_the_provider_is_honoured(waits: list[float]) -> None:
    with simulated(failing_then(429, headers={"Retry-After": "7"})):
        await client().generate(instructions="", user_text="x", output_type=Summary)
    assert waits == [7.0]


async def test_no_retry_when_the_wait_exceeds_the_time_left(waits: list[float]) -> None:
    model = client(RunLimits(max_seconds=5))
    with (
        simulated(failing_then(429, headers={"retry-after-ms": "60000"})),
        pytest.raises(ProviderError),
    ):
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert waits == []
    assert model._tracker.usage.requests == 1


async def test_errors_that_are_not_temporary_are_not_retried(
    waits: list[float],
) -> None:
    model = client()
    with simulated(failing_then(400)), pytest.raises(ProviderError):
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert waits == []
    assert model._tracker.usage.requests == 1


async def test_retries_end_after_the_configured_number(waits: list[float]) -> None:
    model = client(RunLimits(provider_retries=1))
    with simulated(failing_then(503, 503, 503)), pytest.raises(ProviderError):
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert len(waits) == 1
    assert model._tracker.usage.requests == 2


async def test_retries_stay_within_the_request_limit(waits: list[float]) -> None:
    model = client(RunLimits(max_requests=2, provider_retries=5))
    # When the requests run out, the error of the provider is reported, without a
    # wait for an attempt that cannot be made.
    with simulated(failing_then(503, 503, 503)), pytest.raises(ProviderError):
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert model._tracker.usage.requests == 2
    assert len(waits) == 1


async def test_a_single_attempt_call_is_still_retried(waits: list[float]) -> None:
    model = client()
    with simulated(failing_then(503, 503)):
        result = await model.generate(
            instructions="", user_text="x", output_type=Summary, max_attempts=1
        )
    assert result == Summary(summary="ok")
    assert len(waits) == 2
    assert model._tracker.usage.requests == 3


async def test_retries_leave_the_attempts_for_a_valid_output(
    waits: list[float],
) -> None:
    pending: list[Any] = [503, {"wrong": 1}, {"wrong": 2}, {"summary": "ok"}]

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        value = pending.pop(0)
        if isinstance(value, int):
            raise ModelHTTPError(value, MODEL)
        return responder(value)(messages, info)

    model = client()
    with simulated(FunctionModel(respond)):
        result = await model.generate(
            instructions="", user_text="x", output_type=Summary
        )
    assert result == Summary(summary="ok")
    assert model._tracker.usage.requests == 4


async def test_an_error_after_an_answer_is_not_retried(waits: list[float]) -> None:
    pending: list[Any] = [{"wrong": 1}, 503, {"wrong": 2}, {"summary": "ok"}]

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        value = pending.pop(0)
        if isinstance(value, int):
            raise ModelHTTPError(value, MODEL)
        return responder(value)(messages, info)

    model = client()
    # A retry would restart the conversation with two new attempts for a valid
    # output, beyond the two declared, and without the feedback already given.
    with simulated(FunctionModel(respond)), pytest.raises(ProviderError):
        await model.generate(
            instructions="", user_text="x", output_type=Summary, max_attempts=2
        )
    assert waits == []
    assert model._tracker.usage.requests == 2


async def test_a_wait_longer_than_the_cap_is_not_honoured(waits: list[float]) -> None:
    with (
        simulated(failing_then(429, headers={"retry-after": "600"})),
        pytest.raises(ProviderError),
    ):
        await client().generate(instructions="", user_text="x", output_type=Summary)
    assert waits == []


@pytest.mark.parametrize("value", ["Wed, 21 Oct 2026 07:28:00 GMT", "-5"])
async def test_an_unusable_retry_after_falls_back_to_the_computed_wait(
    waits: list[float], value: str
) -> None:
    with simulated(failing_then(429, headers={"retry-after": value})):
        await client().generate(instructions="", user_text="x", output_type=Summary)
    assert len(waits) == 1
    assert 0.5 <= waits[0] <= 1


async def test_a_call_cancelled_while_waiting_counts_its_failed_request() -> None:
    model = client()

    async def cancelled(seconds: float) -> None:
        raise asyncio.CancelledError

    with (
        simulated(failing_then(503)),
        patch.object(client_module, "_sleep", cancelled),
        pytest.raises(asyncio.CancelledError),
    ):
        await model.generate(instructions="", user_text="x", output_type=Summary)
    assert model._tracker.usage.requests == 1


async def test_shared_providers_do_not_retry_and_are_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    await providers.close_providers()
    openai = providers.provider("openai")
    assert providers.provider("openai") is openai
    assert openai.client.max_retries == 0
    assert providers.provider("anthropic").client.max_retries == 0
    first = _resolve_model("openai:gpt-test")
    second = _resolve_model("openai:gpt-test")
    assert first._provider is second._provider is openai
    await providers.close_providers()
    assert openai.client.is_closed()
    assert providers.provider("openai") is not openai
    await providers.close_providers()


async def test_providers_are_closed_when_their_last_holder_releases_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    providers.hold_providers()
    providers.hold_providers()
    openai = providers.provider("openai")
    await providers.release_providers()
    assert not openai.client.is_closed()
    assert providers.provider("openai") is openai
    await providers.release_providers()
    assert openai.client.is_closed()


def test_providers_belong_to_their_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    async def resolved() -> object:
        found = providers.provider("openai")
        await providers.close_providers()
        return found

    assert asyncio.run(resolved()) is not asyncio.run(resolved())


async def test_a_provider_without_credentials_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    await providers.close_providers()
    with pytest.raises(Unavailable):
        await ModelClient(
            ModelSpec(model="ollama:llama-test"), ModelInfo(), tracker()
        ).generate(instructions="", user_text="x", output_type=Summary)


def test_providers_of_a_closed_loop_are_not_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    async def left_open() -> weakref.ref[object]:
        return weakref.ref(providers.provider("openai"))  # never closed

    found = asyncio.run(left_open())
    gc.collect()
    # Keyed by the loop object, so a new loop that reused the id of the closed one
    # would not find it; freed here because no connection was opened.
    assert found() is None
