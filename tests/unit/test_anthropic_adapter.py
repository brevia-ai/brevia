"""The Anthropic adapter with the real SDK and Pydantic AI over a simulated HTTP
transport, and the reasoning that the other adapters cannot apply."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import httpx2
import pytest
from anthropic import AsyncAnthropic
from conftest import simulated
from pydantic import BaseModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.ollama import OllamaProvider

from brevia import ProviderError, RunLimits, Unsupported
from brevia.models import ModelClient
from brevia.models import pydantic_ai as adapter
from brevia.models.limits import LimitTracker
from brevia.models.observed import AnthropicModel
from brevia.models.spec import ModelInfo, ModelSpec

pytestmark = pytest.mark.unit

MODEL = "anthropic:claude-opus-5-5"
INFO = ModelInfo(reasoning_levels=frozenset({"low", "high", "xhigh", "max"}))

Handler = Callable[[dict[str, Any]], httpx2.Response]


class Summary(BaseModel):
    summary: str


def answer(body: dict[str, Any]) -> httpx2.Response:
    """A summary, as a structured output or through the output tool."""
    tools = [tool["name"] for tool in body.get("tools", [])]
    if tools:
        content = [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": tools[0],
                "input": {"summary": "ok"},
            }
        ]
    else:
        content = [{"type": "text", "text": json.dumps({"summary": "ok"})}]
    return httpx2.Response(
        200,
        headers={"request-id": "req_a1"},
        json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": content,
            "stop_reason": "tool_use" if tools else "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    )


def error(status: int, error_type: str, **extra: Any) -> httpx2.Response:
    return httpx2.Response(
        status,
        headers={"request-id": "req_err"},
        json={
            "type": "error",
            "error": {"type": error_type, "message": "limit", **extra},
            "request_id": "req_err",
        },
    )


class Server:
    def __init__(self, handler: Handler) -> None:
        self.bodies: list[dict[str, Any]] = []
        self._handler = handler

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        return self._handler(body)

    @property
    def model(self) -> AnthropicModel:
        client = AsyncAnthropic(
            api_key="test-key",
            base_url="https://api.test",
            max_retries=0,  # Brevia retries, not the SDK
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self)),
        )
        return AnthropicModel(
            "claude-opus-5-5", provider=AnthropicProvider(anthropic_client=client)
        )


def client(**spec: Any) -> ModelClient:
    # Without max_tokens Pydantic AI asks for the maximum output of the model, which it
    # streams: the simulated server answers whole responses only.
    spec.setdefault("max_tokens", 4096)
    return ModelClient(ModelSpec(model=MODEL, **spec), INFO, LimitTracker(RunLimits()))


async def test_max_is_sent_as_the_effort_of_anthropic() -> None:
    server = Server(answer)
    model = client(reasoning="max")
    with simulated(server.model):
        await model.generate(instructions="", user_text="x", output_type=Summary)

    assert server.bodies[0]["output_config"]["effort"] == "max"
    [record] = model._tracker.usage.calls[-1].request_records
    assert record.effective_options["reasoning"] == "max"


async def test_the_request_of_anthropic_is_recorded_with_its_identifier() -> None:
    server = Server(answer)
    model = client()
    with simulated(server.model):
        await model.generate(instructions="", user_text="x", output_type=Summary)

    [record] = model._tracker.usage.calls[-1].request_records
    assert (record.provider, record.request_id) == ("anthropic", "req_a1")
    assert record.response_id == "msg_1"


async def test_debug_logs_of_anthropic_hold_no_contents(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Installed by the request itself, not at import.
    logging.getLogger("anthropic._base_client").filters.clear()
    server = Server(answer)
    model = client()
    with simulated(server.model), caplog.at_level(logging.DEBUG):
        await model.generate(
            instructions="Prompt-7f3a", user_text="Document-9c2e", output_type=Summary
        )

    assert "Document-9c2e" in json.dumps(server.bodies[0])
    assert any(r.name.startswith("anthropic") for r in caplog.records)
    assert "Prompt-7f3a" not in caplog.text
    assert "Document-9c2e" not in caplog.text


@pytest.mark.parametrize(
    "reply",
    [
        error(
            429,
            "rate_limit_error",
            details={"error_code": "enforced_spend_limit_reached"},
        ),
        error(402, "billing_error"),
    ],
    ids=["spend cap", "billing"],
)
async def test_billing_errors_of_anthropic_are_not_retried(
    reply: httpx2.Response, waits: list[float]
) -> None:
    server = Server(lambda body: reply)
    model = client()
    with simulated(server.model), pytest.raises(ProviderError) as caught:
        await model.generate(instructions="", user_text="x", output_type=Summary)

    assert caught.value.retryable is False
    assert len(server.bodies) == 1
    assert waits == []
    [record] = model._tracker.usage.calls[-1].request_records
    assert record.error == "billing"
    assert record.request_id == "req_err"


async def test_a_rate_limit_of_anthropic_is_retried(waits: list[float]) -> None:
    replies = iter([error(429, "rate_limit_error")])
    server = Server(lambda body: next(replies, None) or answer(body))
    model = client()
    with simulated(server.model):
        await model.generate(instructions="", user_text="x", output_type=Summary)

    assert len(server.bodies) == 2
    assert len(waits) == 1
    records = model._tracker.usage.calls[0].request_records
    assert [r.usage_status for r in records] == ["none", "reported"]


def ollama(name: str) -> OpenAIChatModel:
    return OpenAIChatModel(
        name, provider=OllamaProvider(base_url="http://localhost:11434/v1")
    )


@pytest.mark.parametrize(
    ("reference", "model", "reasoning"),
    [
        ("ollama:qwen3:8b", ollama("qwen3:8b"), "max"),
        ("ollama:qwen3:8b", ollama("qwen3:8b"), "low"),
    ],
    ids=["max", "a level the adapter would drop"],
)
async def test_reasoning_that_the_adapter_cannot_apply_is_refused(
    reference: str, model: Any, reasoning: str
) -> None:
    spec = ModelSpec.model_validate({"model": reference, "reasoning": reasoning})
    model_client = ModelClient(spec, INFO, LimitTracker(RunLimits()))
    with (
        patch.object(adapter, "_resolve_model", return_value=model),
        pytest.raises(Unsupported) as caught,
    ):
        await model_client.generate(instructions="", user_text="x", output_type=Summary)

    assert caught.value.details["option"] == "reasoning"


async def test_reasoning_cannot_be_turned_off_on_models_that_always_reason() -> None:
    server = Server(answer)
    with simulated(server.model), pytest.raises(Unsupported):
        await client(reasoning=False).generate(
            instructions="", user_text="x", output_type=Summary
        )

    assert server.bodies == []
