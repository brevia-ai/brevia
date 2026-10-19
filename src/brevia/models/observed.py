"""Record bounded diagnostics at the adapter request boundary."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Literal

from anthropic.types.beta import BetaMessage
from openai.types.responses import Response
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.anthropic import AnthropicModel as PydanticAnthropicModel
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

from brevia.models.options import effective_options
from brevia.models.records import RequestRecord
from brevia.models.spec import ModelSpec

OPENAI_BILLING_ERRORS = frozenset(
    {
        "insufficient_quota",
        "credit_balance_exhausted",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
    }
)
"""Codes and types of the OpenAI errors that a retry cannot fix (HTTP 429)."""

ANTHROPIC_SPEND_CAP = "enforced_spend_limit_reached"
"""``error.details.error_code`` of the 429 of Anthropic at its monthly spend cap."""


def billing_error(provider: str, exc: ModelHTTPError) -> bool:
    """Recognise a billing or spend limit error, without retaining the error body.

    Rate limits share the HTTP status 429 with these errors, which a retry cannot fix:
    for OpenAI the codes of :data:`OPENAI_BILLING_ERRORS`; for Anthropic the status 402
    (``billing_error``) and the 429 at the monthly spend cap. A spend limit set by the
    organization of Anthropic is a 400, never retried.
    """
    body = exc.body
    error = body.get("error", body) if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return provider == "anthropic" and exc.status_code == 402
    if provider == "openai":
        return any(
            isinstance(error.get(key), str) and error[key] in OPENAI_BILLING_ERRORS
            for key in ("code", "type")
        )
    if provider == "anthropic":
        details = error.get("details")
        return exc.status_code == 402 or (
            isinstance(details, dict)
            and details.get("error_code") == ANTHROPIC_SPEND_CAP
        )
    return False


class AnthropicModel(PydanticAnthropicModel):
    """Keep the identifier of the request, which the SDK reads from its header."""

    def _process_response(
        self,
        response: BetaMessage,
        model_request_parameters: ModelRequestParameters,
        model_settings: AnthropicModelSettings,
    ) -> ModelResponse:
        result = super()._process_response(
            response, model_request_parameters, model_settings
        )
        details = {
            **(result.provider_details or {}),
            "brevia_request_id": getattr(response, "_request_id", None),
        }
        return replace(result, provider_details=details)


class OpenAIModel(OpenAIResponsesModel):
    """Preserve SDK diagnostics through the adapter's response-details hook."""

    def _process_provider_details(self, response: Response) -> dict[str, Any]:
        return {
            "brevia_request_id": getattr(response, "_request_id", None),
            "brevia_usage_reported": response.usage is not None,
        }


def _identifier(value: Any) -> str | None:
    # Only bounded diagnostic strings; no arbitrary provider dictionaries retained.
    return value.replace("\x00", "�")[:512] if isinstance(value, str) else None


class ObservedModel(WrapperModel):
    """One call's model, with records shared across its provider retries."""

    def __init__(self, model: Model, spec: ModelSpec, records: list[RequestRecord]):
        super().__init__(model)
        self.spec = spec
        self.records = records

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        started_at, started = datetime.now(UTC), time.monotonic()
        fields: dict[str, Any] = {}
        status: Literal["response", "error", "cancelled"] = "error"
        try:
            response = await self.wrapped.request(
                messages, model_settings, model_request_parameters
            )
            status = "response"
            usage = response.usage
            details = response.provider_details or {}
            reported = details.get("brevia_usage_reported", usage.has_values())
            fields = {
                "returned_model": _identifier(response.model_name),
                "response_id": _identifier(response.provider_response_id),
                "request_id": _identifier(details.get("brevia_request_id")),
                "finish_reason": response.finish_reason,
                "usage_status": "reported" if reported else "unknown",
                "reasoning_tokens": usage.details.get("reasoning_tokens"),
            }
            if reported:
                fields.update(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                )
            return response
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except ModelHTTPError as exc:
            headers = getattr(exc, "headers", None) or {}
            fields = {
                "http_status": exc.status_code,
                "usage_status": "none",
                "request_id": _identifier(
                    headers.get("x-request-id") or headers.get("request-id")
                ),
                "error": "billing"
                if billing_error(self.spec.model.partition(":")[0], exc)
                else "provider",
            }
            raise
        except Exception:
            fields = {"error": "adapter"}
            raise
        finally:
            self.records.append(
                RequestRecord(
                    provider=self.spec.model.partition(":")[0],
                    requested_model=self.spec.model.partition(":")[2],
                    requested_options=self.spec.model_dump(
                        mode="json", exclude={"model"}
                    ),
                    effective_options=effective_options(model_settings or {}),
                    started_at=started_at,
                    seconds=round(time.monotonic() - started, 6),
                    status=status,
                    **fields,
                )
            )
