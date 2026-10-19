"""Structured generation behind a Brevia interface.

Activities call :meth:`ModelClient.generate`; model adapter objects never reach them.
One call produces a validated output of the requested type: the model output is
validated by its schema and by an optional validator, and the problems found are sent
back to the model as a retry, within a bounded number of attempts. Every call,
successful or not, is recorded in the run usage and counted against the run limits.

This module holds the sequence of a call: reserve the budget, generate with retries of
temporary provider errors, account the usage, check the limits. One attempt with the
model is made by the Pydantic AI adapter, :mod:`brevia.models.pydantic_ai`.

A call is described by a :class:`GenerationRequest` and produces a
:class:`GenerationOutcome` instead of raising, so that its usage is always available.
The usage of a call that is cancelled or fails unexpectedly is recorded too.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from brevia.config import defaults
from brevia.db.values import recordable_json, without_nul
from brevia.errors import BreviaError, InvalidInput, ProviderError
from brevia.models.limits import CallContent, CallUsage, LimitTracker
from brevia.models.pydantic_ai import Usage, adapter, attempt
from brevia.models.records import RequestRecord
from brevia.models.spec import ModelInfo, ModelSpec, Prices, check_capabilities

if TYPE_CHECKING:
    from brevia.tools import Tool

logger = logging.getLogger(__name__)

Validator = Callable[[Any], list[str]]
"""Returns the problems found in an output; an empty list accepts it."""

MILLION = Decimal(1_000_000)

RETRY_BASE_SECONDS = 1.0
"""Wait before the first retry of a temporary provider error; doubled each time."""

RETRY_MAX_SECONDS = 30.0
"""Longest wait between two attempts, unless the provider asks for a longer one."""

RETRY_AFTER_MAX_SECONDS = 120.0
"""Longest wait asked by a provider that is honoured; beyond it, no retry."""

RETRY_MARGIN_SECONDS = 1.0
"""Time a retry must leave to the run after its wait, or it is not attempted."""

_sleep = asyncio.sleep  # replaced by tests


@dataclass(frozen=True)
class GenerationRequest:
    """Everything one generation needs, including the budget left in the run."""

    spec: ModelSpec
    instructions: str
    user_text: str
    output_type: type[Any]
    validator: Validator | None
    max_attempts: int
    # Requests reserved for this call; None for these four: no limit in the run.
    request_limit: int | None
    tool_calls_limit: int | None
    token_limit: int | None
    timeout: float | None
    prices: Prices | None
    provider_retries: int = 0  # retries of temporary provider errors
    tools: tuple[Tool, ...] = ()
    tool_context: Any = None  # RunContext given to the tools
    records: list[RequestRecord] = field(default_factory=list)


@dataclass(frozen=True)
class GenerationOutcome:
    """Result of one generation: output or error, with the usage in both cases."""

    usage: CallUsage
    output: Any = None
    error: BreviaError | None = None


def estimate_cost(usage: Usage, prices: Prices | None) -> Decimal | None:
    """Cost in USD from the declared prices, or ``None`` if a needed price is unknown.

    Cache reads and writes are part of the input tokens, so they are priced
    separately and removed from the ordinary input.
    """
    if prices is None:
        return None
    if usage.cache_read_tokens and prices.cached_input is None:
        return None
    if usage.cache_write_tokens and prices.cache_write is None:
        return None
    ordinary = usage.input_tokens - usage.cache_read_tokens - usage.cache_write_tokens
    cost = (
        Decimal(ordinary) * prices.input + Decimal(usage.output_tokens) * prices.output
    )
    if usage.cache_read_tokens and prices.cached_input is not None:
        cost += Decimal(usage.cache_read_tokens) * prices.cached_input
    if usage.cache_write_tokens and prices.cache_write is not None:
        cost += Decimal(usage.cache_write_tokens) * prices.cache_write
    return cost / MILLION


def _json_or_none(value: Any) -> Any:
    """JSON form of an output for the record of its call.

    NUL characters, which PostgreSQL refuses, become U+FFFD; an output without a
    finite JSON form is recorded as ``None``.
    """
    try:
        return recordable_json(value)
    except (TypeError, ValueError):
        return None


def _call_usage(
    request: GenerationRequest, usage: Usage, started: float, error: str | None
) -> CallUsage:
    seconds = time.monotonic() - started
    return CallUsage(
        model=request.spec.model,
        options=_options(request),
        started_at=datetime.now(UTC) - timedelta(seconds=seconds),
        requests=max(usage.requests, len(request.records)),
        tool_calls=usage.tool_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        cost_usd=(
            None
            if any(r.usage_status == "unknown" for r in request.records)
            else estimate_cost(usage, request.prices)
        ),
        prices=request.prices,
        seconds=round(seconds, 3),
        error=error,
        # Read during the call: a fake may be removed before the outcome is written.
        adapter=adapter(),
        request_records=tuple(request.records),
    )


async def generate_once(
    request: GenerationRequest, usage: Usage, started: float
) -> GenerationOutcome:
    """Run one generation with the adapter, retrying temporary provider errors.

    A retryable ``ProviderError`` (rate limits, server errors, connection problems)
    is retried up to ``request.provider_retries`` times, with waits that double from
    :data:`RETRY_BASE_SECONDS` up to :data:`RETRY_MAX_SECONDS`, or as long as the
    provider asks (``Retry-After``); never beyond the time left to the run. Each
    failed request counts as one request of ``usage``, so retries stay within the
    request limit of the call, which reserves them besides the attempts for a valid
    output (``request.max_attempts``). A provider asking for a wait longer than
    :data:`RETRY_AFTER_MAX_SECONDS` is not retried, and neither is an error after the
    model has answered in the same attempt, for example after an invalid output: a
    retry would restart the attempts for a valid output.

    ``usage`` is updated in place, so the caller keeps the usage of a call that is
    cancelled or raises. Provider messages and error bodies are not copied into the
    error: they may contain request data. Cancellation and unexpected exceptions
    propagate.
    """
    for retry in range(request.provider_retries + 1):
        before = usage.requests  # responses received so far
        result = await attempt(request, usage)
        error, retry_after = result.error, result.retry_after
        if error is None:
            return GenerationOutcome(
                usage=_call_usage(request, usage, started, None), output=result.output
            )
        if not isinstance(error, ProviderError):
            return GenerationOutcome(
                usage=_call_usage(request, usage, started, error.code), error=error
            )
        answered = usage.requests > before
        usage.requests += 1  # a failed request was sent, and may have been billed
        outcome = GenerationOutcome(
            usage=_call_usage(request, usage, started, error.code), error=error
        )
        if not error.retryable or retry == request.provider_retries:
            return outcome
        if answered:
            # A new attempt would start the conversation again, with all the
            # attempts for a valid output and without the feedback given so far.
            return outcome
        if (
            request.request_limit is not None
            and usage.requests >= request.request_limit
        ):
            return outcome  # no request left for another attempt
        if retry_after is not None and retry_after > RETRY_AFTER_MAX_SECONDS:
            return outcome  # the provider asks for a wait longer than worth holding
        backoff = min(RETRY_BASE_SECONDS * 2**retry, RETRY_MAX_SECONDS)
        wait = max(backoff * random.uniform(0.5, 1), retry_after or 0)  # noqa: S311
        left = (
            None
            if request.timeout is None
            else request.timeout - (time.monotonic() - started)
        )
        if left is not None and wait + RETRY_MARGIN_SECONDS > left:
            return outcome  # no time left for another attempt
        logger.warning(
            "Model provider error %s, attempt %d of %d, retried in %.1f s",
            error.details.get("status_code", error.code),
            retry + 1,
            request.provider_retries + 1,
            wait,
        )
        await _sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


def with_content(
    call: CallUsage, request: GenerationRequest, outcome: GenerationOutcome | None
) -> CallUsage:
    """``call`` with the contents of the call: instructions, user text and output."""
    output = None
    if outcome is not None and outcome.error is None:
        output = _json_or_none(outcome.output)
    instructions = without_nul(request.instructions)
    user_text = without_nul(request.user_text)
    content = CallContent(instructions, user_text, output)
    return replace(call, content=content)


def _options(request: GenerationRequest) -> dict[str, Any]:
    """Options recorded with a call: the model use and the tools offered."""
    options = request.spec.model_dump(mode="json", exclude={"model"})
    if request.tools:
        options["tools"] = [tool.name for tool in request.tools]
    return options


class ModelClient:
    """A configured model available to one run.

    Created by the run context; activities obtain it with ``ctx.model()``.
    """

    def __init__(
        self,
        spec: ModelSpec,
        info: ModelInfo,
        tracker: LimitTracker,
        log_context: Mapping[str, str] | None = None,
        capture: bool = False,
        context: Any = None,
    ) -> None:
        check_capabilities(spec, info)
        self.spec = spec
        self._info = info
        self._tracker = tracker
        self._log_context = dict(log_context or {})
        self._capture = capture
        self._context = context  # the RunContext, given to tools

    async def generate[OutputT](
        self,
        *,
        instructions: str,
        user_text: str,
        output_type: type[OutputT],
        validator: Validator | None = None,
        max_attempts: int = defaults.GENERATION_MAX_ATTEMPTS,
        max_output_tokens: int | None = None,
        tools: Sequence[Tool] = (),
    ) -> OutputT:
        """Generate a validated output of type ``output_type``.

        Args:
            instructions: Stable instructions for the model, usually a rendered prompt.
            user_text: Data of this request.
            output_type: Expected output, typically a Pydantic model. Type checkers
                infer the result from a class or a parametrised generic; unions,
                ``Annotated`` and ``Literal`` work at run time but need a ``cast``.
            validator: Further checks on the output; its problems are sent back to
                the model as a retry.
            max_attempts: Attempts allowed to obtain a valid output.
            max_output_tokens: Overrides the ``max_tokens`` of the model use.
            tools: Tools the model may call before it answers (see
                :mod:`brevia.tools`); their calls count against ``max_tool_calls``.

        Raises:
            OutputInvalid: No valid output within ``max_attempts``.
            LimitExceeded: A run limit was reached, also when concurrent calls
                together went over the tokens or tool calls of the run: each call
                that finishes over the limit raises it, and its output is discarded.
            RunTimeout: The run exceeded its maximum duration.
            ProviderError: The model provider returned an error.
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        names = [tool.name for tool in tools]
        if len(set(names)) != len(names):
            raise ValueError(f"Tool names must be different: {names}")
        if tools and self._context is None:
            raise ValueError("Tools need a model obtained from the run: ctx.model()")
        spec = self.spec
        if max_output_tokens is not None:
            # model_copy(update=...) does not validate: build a validated spec.
            try:
                spec = ModelSpec.model_validate(
                    {**spec.model_dump(), "max_tokens": max_output_tokens}
                )
            except ValidationError:
                raise InvalidInput(
                    "max_output_tokens is not valid",
                    {"max_output_tokens": max_output_tokens},
                ) from None
        # Tool turns are independent of output corrections. Reserve an upper bound
        # (one request per permitted tool call) atomically, including the final
        # output and provider retries. Concurrent generations cannot share it.
        # Without a limit of tool calls, a call with tools reserves every request left.
        limits = self._tracker.limits
        budget = self._tracker.reserve(
            None
            if tools and not limits.max_tool_calls
            else max_attempts
            + limits.provider_retries
            + (limits.max_tool_calls if tools else 0)
        )
        request = GenerationRequest(
            spec=spec,
            instructions=instructions,
            user_text=user_text,
            output_type=output_type,
            validator=validator,
            max_attempts=max_attempts,
            request_limit=budget.requests,
            tool_calls_limit=budget.tool_calls,
            token_limit=budget.tokens,
            timeout=budget.seconds,
            prices=self._info.prices,
            provider_retries=self._tracker.limits.provider_retries,
            tools=tuple(tools),
            tool_context=self._context,
        )
        usage, started = Usage(), time.monotonic()
        call: CallUsage | None = None
        try:
            outcome = await generate_once(request, usage, started)
            call = self._captured(outcome.usage, request, outcome)
        except BaseException as exc:
            # Requests already sent are billed: count them, then let the error go on.
            code = (
                "cancelled" if isinstance(exc, asyncio.CancelledError) else "internal"
            )
            call = self._captured(
                _call_usage(request, usage, started, code), request, None
            )
            raise
        finally:
            self._tracker.release(budget, call)
            if call is not None:
                self._log_call(call)
        # A deadline passed during the call is a run timeout, whatever the outcome.
        self._tracker.seconds_left()
        if outcome.error is not None:
            raise outcome.error  # its own error is more precise than the totals
        # Concurrent calls may together have gone over a limit: the output of a call
        # that finishes over it is discarded, its usage stays counted.
        self._tracker.check_totals()
        output: OutputT = outcome.output
        return output

    def _captured(
        self,
        call: CallUsage,
        request: GenerationRequest,
        outcome: GenerationOutcome | None,
    ) -> CallUsage:
        """``call`` with its contents, when the activity captures them."""
        return with_content(call, request, outcome) if self._capture else call

    def _log_call(self, call: CallUsage) -> None:
        logger.info(
            "Model call %s: %d requests, %d input and %d output tokens, %.3f s%s",
            call.model,
            call.requests,
            call.input_tokens,
            call.output_tokens,
            call.seconds,
            f", failed with {call.error}" if call.error else "",
            extra=self._log_context,
        )
