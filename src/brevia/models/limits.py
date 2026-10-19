"""Per-run limits and usage.

Limits apply to a whole run, failed attempts included: model requests, tool calls,
tokens and time. Some usage is known only after a response, so a limit stops the run
at the first check that finds it exceeded; it is not an exact cap on tokens or cost.
A limit set to ``0`` is off.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from brevia.config import defaults
from brevia.errors import LimitExceeded, RunTimeout
from brevia.models.records import RequestRecord
from brevia.models.spec import Prices


class RunLimits(BaseModel):
    """Limits of one run; ``0`` turns a limit off."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_requests: int = Field(
        default=defaults.RUN_MAX_REQUESTS, ge=0, description="Model requests."
    )
    max_tool_calls: int = Field(
        default=defaults.RUN_MAX_TOOL_CALLS, ge=0, description="Tool invocations."
    )
    max_total_tokens: int = Field(
        default=defaults.RUN_MAX_TOTAL_TOKENS,
        ge=0,
        description="Input and output tokens.",
    )
    max_seconds: float = Field(
        default=defaults.RUN_MAX_SECONDS, ge=0, description="Duration of the run."
    )
    provider_retries: int = Field(
        default=defaults.RUN_PROVIDER_RETRIES,
        ge=0,
        le=10,
        description="Retries of a model request after a temporary provider error "
        "(rate limit, server error, connection problem); each attempt is a request.",
    )


@dataclass(frozen=True)
class CallContent:
    """Contents of one model call, kept only when the activity captures them.

    ``output`` is the JSON form of the validated output, or ``None`` when the call
    failed.
    """

    instructions: str
    user_text: str
    output: Any


@dataclass(frozen=True)
class CallUsage:
    """Usage of one model call, including all its attempts.

    Token counters are those reported through the model adapter. ``cost_usd`` is an
    estimate from ``prices``, the declared prices used, or ``None`` when a needed price
    is unknown. ``options`` are the effective options of the call (reasoning,
    temperature, maximum output tokens), which overrides may have changed from the
    configuration recorded in the snapshot.
    """

    model: str
    options: dict[str, Any]
    started_at: datetime
    requests: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: Decimal | None
    prices: Prices | None
    seconds: float
    error: str | None = None
    content: CallContent | None = None
    adapter: Mapping[str, str] | None = None
    """Model adapter that made the call: ``fake`` when a fake answered it."""
    request_records: tuple[RequestRecord, ...] = ()
    """Individual requests; adapter version and prices are shared by the call."""


@dataclass
class Usage:
    """Usage of a run: the sum of its calls.

    The cost becomes ``None`` as soon as one call has an unknown cost: a partial sum
    would understate it.
    """

    requests: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: Decimal | None = Decimal(0)
    calls: list[CallUsage] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, call: CallUsage) -> None:
        self.requests += call.requests
        self.tool_calls += call.tool_calls
        self.input_tokens += call.input_tokens
        self.output_tokens += call.output_tokens
        self.cache_read_tokens += call.cache_read_tokens
        self.cache_write_tokens += call.cache_write_tokens
        if self.cost_usd is not None and call.cost_usd is not None:
            self.cost_usd += call.cost_usd
        else:
            self.cost_usd = None
        self.calls.append(call)

    def as_dict(self) -> dict[str, Any]:
        """Summary of the run usage, without the individual calls."""
        return {
            "requests": self.requests,
            "tool_calls": self.tool_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cost_usd": None if self.cost_usd is None else str(self.cost_usd),
            "cost_kind": "unknown" if self.cost_usd is None else "estimate",
        }


@dataclass(frozen=True)
class Remaining:
    """Budget left for the next model call; ``None`` where the run has no limit."""

    requests: int | None
    tool_calls: int | None
    tokens: int | None
    seconds: float | None


class LimitTracker:
    """Enforces the limits of one run and accumulates its usage.

    Elapsed time is measured from the creation of the tracker in the current process;
    ``seconds`` is the time left to a job, from its recorded deadline, when it
    starts again after an interruption.
    """

    def __init__(self, limits: RunLimits, seconds: float | None = None) -> None:
        self.limits = limits
        self.usage = Usage()
        self.seconds: float | None = (
            (limits.max_seconds or None) if seconds is None else seconds
        )
        self._started = time.monotonic()
        self._reserved_requests = 0

    def seconds_left(self) -> float | None:
        """Seconds left in the run; ``None`` without a time limit.

        Raises:
            RunTimeout: The run exceeded its maximum duration.
        """
        if self.seconds is None:
            return None
        left = self.seconds - (time.monotonic() - self._started)
        if left <= 0:
            raise RunTimeout(
                f"Run exceeded its maximum duration of {self.limits.max_seconds} s",
                {"max_seconds": self.limits.max_seconds},
            )
        return left

    def reserve(self, attempts: int | None) -> Remaining:
        """Reserve the requests of one model call and return its budget.

        Requests are reserved at once, so that calls running concurrently in the same
        run cannot spend the same budget; ``attempts`` ``None`` reserves all the
        requests left. Tokens cannot be reserved, because they are known only after a
        response: each call receives the tokens left when it starts. Every reservation
        must be released with :meth:`release`.

        Raises:
            RunTimeout: The run exceeded its maximum duration.
            LimitExceeded: No requests or tokens are left.
        """
        seconds = self.seconds_left()
        limits = self.limits
        requests = (
            limits.max_requests - self.usage.requests - self._reserved_requests
            if limits.max_requests
            else None
        )
        tokens = (
            limits.max_total_tokens - self.usage.total_tokens
            if limits.max_total_tokens
            else None
        )
        if (requests is not None and requests <= 0) or (
            tokens is not None and tokens <= 0
        ):
            raise LimitExceeded(
                "Run limit of model requests or tokens reached",
                {
                    "usage": self.usage.as_dict(),
                    "limits": self.limits.model_dump(),
                },
            )
        granted = (
            requests
            if attempts is None
            else attempts
            if requests is None
            else min(attempts, requests)
        )
        self._reserved_requests += granted or 0
        tool_calls = (
            max(limits.max_tool_calls - self.usage.tool_calls, 0)
            if limits.max_tool_calls
            else None
        )
        return Remaining(granted, tool_calls, tokens, seconds)

    def check_totals(self) -> None:
        """Check the totals known so far against the limits.

        Calls running concurrently each receive the tokens and tool calls left when
        they start, so together they may exceed the limits: this is detected once
        their usage is known.

        Raises:
            LimitExceeded: The tokens or the tool calls of the run exceed their limit.
        """
        usage, limits = self.usage, self.limits
        if (
            limits.max_total_tokens and usage.total_tokens > limits.max_total_tokens
        ) or (limits.max_tool_calls and usage.tool_calls > limits.max_tool_calls):
            raise LimitExceeded(
                "Run limit of tokens or tool calls exceeded",
                {"usage": usage.as_dict(), "limits": self.limits.model_dump()},
            )

    def release(self, budget: Remaining, call: CallUsage | None) -> None:
        """Release a reservation and add the usage of the call, if it completed."""
        self._reserved_requests -= budget.requests or 0
        if call is not None:
            self.usage.add(call)
