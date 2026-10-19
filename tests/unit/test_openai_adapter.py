"""The OpenAI adapter with the real SDK and Pydantic AI over a simulated HTTP transport.

No request leaves the process: the transport answers as the Responses API does, and
records the payload that the SDK would send.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx2
import pytest
from conftest import simulated
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai.providers.openai import OpenAIProvider

from brevia import (
    LimitExceeded,
    OutputInvalid,
    ProviderError,
    RunLimits,
    Unsupported,
)
from brevia.models import ModelClient
from brevia.models.limits import LimitTracker
from brevia.models.observed import OpenAIModel
from brevia.models.spec import ModelInfo, ModelSpec, Prices
from brevia.tools import Tool

pytestmark = pytest.mark.unit

MODEL = "openai:gpt-6-luna"
INFO = ModelInfo(
    reasoning_levels=frozenset({"low", "medium", "high", "max"}),
    temperature=True,
    temperature_with_reasoning=True,  # the adapter, not the project, refuses it
    prices=Prices(input=Decimal(1), output=Decimal(2), cached_input=Decimal("0.5")),
)

Handler = Callable[[dict[str, Any]], httpx2.Response]


class Summary(BaseModel):
    summary: str


def response(
    output: list[dict[str, Any]],
    *,
    status: str = "completed",
    usage: dict[str, Any] | None = None,
    **fields: Any,
) -> httpx2.Response:
    body: dict[str, Any] = {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "status": status,
        "model": "gpt-6-luna-2026-09-01",
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        **fields,
    }
    if usage is not None:
        body["usage"] = usage
    return httpx2.Response(200, headers={"x-request-id": "req_123"}, json=body)


USAGE = {
    "input_tokens": 10,
    "input_tokens_details": {"cached_tokens": 4},
    "output_tokens": 7,
    "output_tokens_details": {"reasoning_tokens": 5},
    "total_tokens": 17,
}


def call(name: str, arguments: dict[str, Any], number: int = 1) -> dict[str, Any]:
    return {
        "type": "function_call",
        "id": f"fc_{number}",
        "call_id": f"call_{number}",
        "name": name,
        "arguments": json.dumps(arguments),
        "status": "completed",
    }


def answer(body: dict[str, Any], text: str = "ok") -> httpx2.Response:
    """The output tool of the request, called with a summary."""
    output_tool = next(t["name"] for t in body["tools"] if t["name"] == "final_result")
    return response([call(output_tool, {"summary": text})], usage=USAGE)


def billing_or_rate(code: str | None, error_type: str = "requests") -> httpx2.Response:
    """A 429 of OpenAI; ``code`` and ``type`` vary independently."""
    return httpx2.Response(
        429,
        headers={"x-request-id": "req_429"},
        json={"error": {"message": "limit", "type": error_type, "code": code}},
    )


class Server:
    """Answers with ``handler`` and keeps the JSON bodies the SDK sent."""

    def __init__(self, handler: Handler) -> None:
        self.bodies: list[dict[str, Any]] = []
        self._handler = handler

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        return self._handler(body)

    @property
    def model(self) -> OpenAIModel:
        client = AsyncOpenAI(
            api_key="test-key",
            base_url="https://api.test/v1",
            max_retries=0,  # Brevia retries, not the SDK
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self)),
        )
        return OpenAIModel("gpt-6-luna", provider=OpenAIProvider(openai_client=client))


@pytest.fixture
def serve() -> Callable[[Handler], Server]:
    return Server


def client(context: Any = None, **spec: Any) -> ModelClient:
    return ModelClient(
        ModelSpec(model=MODEL, **spec),
        INFO,
        LimitTracker(RunLimits()),
        context=context,
    )


async def test_the_payload_keeps_no_copy_and_the_call_records_its_request(
    serve: Callable[[Handler], Server],
) -> None:
    server = serve(answer)
    model = client(reasoning="low")
    with simulated(server.model):
        result = await model.generate(
            instructions="Summarise.", user_text="x", output_type=Summary
        )

    assert result == Summary(summary="ok")
    [body] = server.bodies
    assert body["store"] is False
    assert body["reasoning"]["effort"] == "low"
    assert "max_output_tokens" not in body  # no limit: the maximum of the model
    assert "temperature" not in body
    assert "reasoning.encrypted_content" in body["include"]
    [record] = model._tracker.usage.calls[-1].request_records
    assert record.status == "response"
    assert record.returned_model == "gpt-6-luna-2026-09-01"
    assert record.response_id == "resp_1"
    assert record.request_id == "req_123"
    assert (record.input_tokens, record.output_tokens) == (10, 7)
    assert (record.reasoning_tokens, record.cache_read_tokens) == (5, 4)
    assert record.effective_options == {
        "reasoning": "low",
        "store": False,
    }


@pytest.mark.parametrize(
    ("reasoning", "effort"), [(True, "medium"), (False, "none"), ("max", "max")]
)
async def test_reasoning_is_sent_as_the_effort_it_names(
    serve: Callable[[Handler], Server], reasoning: Any, effort: str
) -> None:
    server = serve(answer)
    with simulated(server.model):
        await client(reasoning=reasoning).generate(
            instructions="", user_text="x", output_type=Summary
        )

    assert server.bodies[0]["reasoning"]["effort"] == effort


async def test_temperature_with_reasoning_is_refused_before_any_request(
    serve: Callable[[Handler], Server],
) -> None:
    server = serve(answer)
    with simulated(server.model), pytest.raises(Unsupported) as caught:
        await client(reasoning="low", temperature=0.2).generate(
            instructions="", user_text="x", output_type=Summary
        )

    assert caught.value.details["option"] == "temperature"
    assert server.bodies == []


async def test_a_max_tokens_of_the_model_use_is_sent(
    serve: Callable[[Handler], Server],
) -> None:
    server = serve(answer)
    with simulated(server.model):
        await client(max_tokens=2000).generate(
            instructions="", user_text="x", output_type=Summary
        )

    assert server.bodies[0]["max_output_tokens"] == 2000


async def test_a_rate_limit_is_retried(
    serve: Callable[[Handler], Server], waits: list[float]
) -> None:
    replies = iter([billing_or_rate("rate_limit_exceeded", "rate_limit_error")])
    server = serve(lambda body: next(replies, None) or answer(body))
    model = client()
    with simulated(server.model):
        await model.generate(instructions="", user_text="x", output_type=Summary)

    assert len(server.bodies) == 2
    assert len(waits) == 1
    call_usage = model._tracker.usage.calls[0]
    records = call_usage.request_records
    # Both requests are records of the same call: the failed one and its retry.
    assert [r.status for r in records] == ["error", "response"]
    # The rate limit generated nothing to bill: the cost of the call stays known.
    assert [r.usage_status for r in records] == ["none", "reported"]
    assert call_usage.cost_usd is not None


@pytest.mark.parametrize(
    ("code", "error_type"),
    [
        ("credit_balance_exhausted", "requests"),
        ("organization_spend_limit_exceeded", "requests"),
        ("project_spend_limit_exceeded", "requests"),
        ("organization_usage_limit_exceeded", "requests"),
        ("insufficient_quota", "requests"),
        (None, "insufficient_quota"),
    ],
)
async def test_billing_errors_are_not_retried(
    serve: Callable[[Handler], Server],
    waits: list[float],
    code: str | None,
    error_type: str,
) -> None:
    server = serve(lambda body: billing_or_rate(code, error_type))
    model = client()
    with simulated(server.model), pytest.raises(ProviderError) as caught:
        await model.generate(instructions="", user_text="x", output_type=Summary)

    assert caught.value.retryable is False
    assert len(server.bodies) == 1
    assert waits == []
    [record] = model._tracker.usage.calls[-1].request_records
    assert (record.http_status, record.error) == (429, "billing")
    assert record.request_id == "req_429"


async def test_a_response_cut_at_max_tokens_is_reported_without_retries(
    serve: Callable[[Handler], Server],
) -> None:
    server = serve(
        lambda body: response(
            [],
            status="incomplete",
            incomplete_details={"reason": "max_output_tokens"},
            usage=USAGE,
        )
    )
    model = client(max_tokens=100)
    with simulated(server.model), pytest.raises(OutputInvalid) as caught:
        await model.generate(instructions="", user_text="x", output_type=Summary)

    assert caught.value.details == {"reason": "max_tokens"}
    assert len(server.bodies) == 1
    [record] = model._tracker.usage.calls[-1].request_records
    assert record.finish_reason == "length"
    assert record.reasoning_tokens == 5  # paid, without an answer


async def test_a_response_without_usage_has_an_unknown_cost(
    serve: Callable[[Handler], Server],
) -> None:
    def no_usage(body: dict[str, Any]) -> httpx2.Response:
        reply = answer(body)
        data = json.loads(reply.content)
        del data["usage"]
        return httpx2.Response(200, json=data)

    server = serve(no_usage)
    model = client()
    with simulated(server.model):
        await model.generate(instructions="", user_text="x", output_type=Summary)

    call_usage = model._tracker.usage.calls[-1]
    assert call_usage.request_records[0].usage_status == "unknown"
    assert call_usage.cost_usd is None


class Context:
    """The part of a run context that the tools of this test use."""

    log = logging.LoggerAdapter(logging.getLogger("test.tools"), {})


async def count(ctx: Any, number: int) -> int:
    return number


COUNT = Tool(name="count", description="Echo a number.", function=count)


async def test_a_sequence_of_tool_calls_longer_than_the_attempts_completes(
    serve: Callable[[Handler], Server],
) -> None:
    # Seven requests: six tool calls, then the answer. The attempts of a call (3)
    # and the provider retries (2) do not limit the turns with tools.
    turns = iter(range(1, 7))

    def handler(body: dict[str, Any]) -> httpx2.Response:
        number = next(turns, None)
        if number is None:
            return answer(body)
        return response([call("count", {"number": number}, number)], usage=USAGE)

    server = serve(handler)
    model = client(context=Context())
    with simulated(server.model):
        result = await model.generate(
            instructions="", user_text="x", output_type=Summary, tools=[COUNT]
        )

    assert result == Summary(summary="ok")
    assert len(server.bodies) == 7
    usage = model._tracker.usage
    assert usage.tool_calls == 6
    assert len(usage.calls[-1].request_records) == 7


async def test_the_encrypted_reasoning_goes_back_with_the_next_turn(
    serve: Callable[[Handler], Server],
) -> None:
    # OpenAI stores nothing (store: false): the reasoning of a tool turn is returned
    # encrypted and must travel with the following request, not by reference.
    reasoning = {
        "type": "reasoning",
        "id": "rs_1",
        "encrypted_content": "sealed-reasoning",
        "summary": [],
    }
    turns = iter([response([reasoning, call("count", {"number": 1})], usage=USAGE)])
    server = serve(lambda body: next(turns, None) or answer(body))
    model = client(context=Context(), reasoning="low")
    with simulated(server.model):
        await model.generate(
            instructions="", user_text="x", output_type=Summary, tools=[COUNT]
        )

    first, second = server.bodies
    assert first["store"] is False
    assert "previous_response_id" not in second
    sent_back = [item for item in second["input"] if item.get("type") == "reasoning"]
    assert [item["encrypted_content"] for item in sent_back] == ["sealed-reasoning"]


async def test_tool_turns_still_stop_at_the_requests_of_the_run(
    serve: Callable[[Handler], Server],
) -> None:
    def handler(body: dict[str, Any]) -> httpx2.Response:
        return response([call("count", {"number": 1})], usage=USAGE)

    server = serve(handler)
    model = ModelClient(
        ModelSpec(model=MODEL),
        INFO,
        LimitTracker(RunLimits(max_requests=4)),
        context=Context(),
    )
    with simulated(server.model), pytest.raises(LimitExceeded):
        await model.generate(
            instructions="", user_text="x", output_type=Summary, tools=[COUNT]
        )

    assert len(server.bodies) == 4


async def test_without_reasoning_the_model_default_applies(
    serve: Callable[[Handler], Server],
) -> None:
    server = serve(answer)
    with simulated(server.model):
        await client().generate(instructions="", user_text="x", output_type=Summary)

    assert "effort" not in (server.bodies[0].get("reasoning") or {})
