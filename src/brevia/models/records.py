"""Provider-neutral records of individual model requests, without their contents."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RequestRecord(BaseModel):
    """Diagnostics of one attempt, including failures and cancellations.

    Missing counters mean unknown, not zero. Cache counters are subsets of input;
    reasoning tokens are a subset of output. ``usage_status`` describes whether
    input/output usage was reported, not whether every optional detail is present:
    ``none`` for an HTTP error answer of the provider, which generates nothing to bill;
    ``unknown`` when a request may have been billed without a usage report (no usage
    in the response, cancellation, timeout or lost connection).
    Effective options contain only settings Brevia knows the adapter applies;
    omitted provider defaults remain unknown. No prompt, response, tool arguments,
    arbitrary headers or provider error bodies are retained here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    requested_model: str
    returned_model: str | None = None
    requested_options: dict[str, Any]
    effective_options: dict[str, Any]
    started_at: datetime
    seconds: float
    status: Literal["response", "error", "cancelled"]
    response_id: str | None = None
    request_id: str | None = None
    http_status: int | None = None
    finish_reason: str | None = None
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    usage_status: Literal["reported", "unknown", "none"] = "unknown"
