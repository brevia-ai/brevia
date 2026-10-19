"""Pydantic AI adapter: one attempt of a structured generation.

:func:`attempt` runs one generation with a single stateless Pydantic AI agent: the
output is validated by its schema and by the optional validator, and the problems found
are sent back to the model as a retry, within the attempts of the request. Pydantic AI
exceptions are translated into Brevia errors here, and Pydantic AI objects do not leave
this module, except the usage counters (:data:`Usage`). The sequence around an attempt
(provider retries, usage, limits) is in :mod:`brevia.models.client`.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import version
from typing import TYPE_CHECKING, Any, get_type_hints

from pydantic import ValidationError
from pydantic_ai import Agent, ModelRetry, UsageLimits, capture_run_messages
from pydantic_ai import RunContext as AgentContext
from pydantic_ai import Tool as AgentTool
from pydantic_ai.exceptions import (
    ContentFilterError,
    IncompleteToolCall,
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UserError,
)
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, infer_model
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import RunUsage

from brevia.errors import (
    BreviaError,
    LimitExceeded,
    OutputInvalid,
    ProviderError,
    Unavailable,
    Unsupported,
    cause_types,
)
from brevia.models import fake
from brevia.models.observed import (
    AnthropicModel,
    ObservedModel,
    OpenAIModel,
    billing_error,
)
from brevia.models.options import settings_for
from brevia.models.providers import guard_sdk_logs, provider
from brevia.models.spec import ModelSpec

if TYPE_CHECKING:
    from brevia.models.client import GenerationRequest, Validator
    from brevia.tools import Tool

Usage = RunUsage
"""Usage counters of a call, updated in place by :func:`attempt`."""

ADAPTER = {"name": "pydantic-ai", "version": version("pydantic-ai-slim")}
"""Model adapter recorded in run snapshots (specification §7.4)."""

RETRYABLE_HTTP_STATUSES = frozenset({408, 409, 429})
"""Client errors worth retrying; every 5xx status is retryable too."""


def adapter() -> dict[str, str]:
    """The model adapter in use: Pydantic AI, or the fake when one is installed."""
    return dict(fake.ADAPTER if fake.installed() is not None else ADAPTER)


@dataclass(frozen=True)
class Attempt:
    """Outcome of one attempt: output or error, and the wait the provider asked for."""

    output: Any = None
    error: BreviaError | None = None
    retry_after: float | None = None


@dataclass
class _Deps:
    validator: Validator | None
    last_problems: list[str] = field(default_factory=list)


# Configured per run (model, output type, instructions, settings); it holds no state.
_AGENT: Agent[_Deps, Any] = Agent(
    None, deps_type=_Deps, name="brevia.generate", defer_model_check=True
)


def _output_function(output_type: type[Any]) -> Callable[..., Any]:
    """Output function that validates with ``output_type`` and then with the validator.

    Pydantic AI does not accept a per-run output type on an agent with output
    validators; an output function keeps the schema of ``output_type`` and lets a
    single stateless agent serve every call.
    """

    def output(ctx: AgentContext[_Deps], value: Any) -> Any:
        problems = ctx.deps.validator(value) if ctx.deps.validator else []
        ctx.deps.last_problems = problems  # problems of the latest validator check
        if problems:
            raise ModelRetry("Fix the result: " + "; ".join(problems) + ".")
        return value

    output.__annotations__ = {
        "ctx": AgentContext[_Deps],
        "value": output_type,
        "return": output_type,
    }
    # The docstring becomes the description of the output for the model: use it only
    # when the type defines its own, not the one inherited from a built-in type.
    documented = isinstance(output_type, type) and output_type.__module__ != "builtins"
    output.__doc__ = output_type.__dict__.get("__doc__") if documented else None
    return output


def _toolsets(request: GenerationRequest) -> list[FunctionToolset[_Deps]] | None:
    """The Brevia tools of the request as a Pydantic AI toolset."""
    if not request.tools:
        return None
    return [
        FunctionToolset(
            [_agent_tool(tool, request.tool_context) for tool in request.tools]
        )
    ]


def _agent_tool(tool: Tool, context: Any) -> AgentTool[_Deps]:
    """A Pydantic AI tool that calls ``tool.function`` with the context of the run.

    The schema of the arguments comes from the parameters after the first one. A
    :class:`~brevia.tools.ToolRetry` goes back to the model as a retry; any other
    error stops the generation and the run.
    """
    # Imported here: brevia.tools depends on the run context, which uses this module.
    from brevia.tools import ToolRetry

    signature = inspect.signature(tool.function)
    try:
        hints = get_type_hints(tool.function)
    except NameError:
        raise ValueError(
            f"Tool {tool.name!r}: the annotations of its function must be available "
            "at run time, not only when type checking"
        ) from None
    parameters = list(signature.parameters.values())[1:]

    async def call(**arguments: Any) -> Any:
        started = time.monotonic()
        outcome = "ok"
        try:
            return await tool.function(context, **arguments)
        except ToolRetry as exc:
            outcome = "retry"
            raise ModelRetry(str(exc)) from None
        except BaseException as exc:
            outcome = exc.code if isinstance(exc, BreviaError) else "error"
            raise
        finally:
            context.log.info(
                "Tool %s: %s in %.3f s", tool.name, outcome, time.monotonic() - started
            )

    call.__signature__ = signature.replace(parameters=parameters)  # type: ignore[attr-defined]
    call.__annotations__ = {
        parameter.name: hints.get(parameter.name, Any) for parameter in parameters
    } | {"return": hints.get("return", Any)}
    return AgentTool(
        call, takes_ctx=False, name=tool.name, description=tool.description
    )


def _resolve_model(reference: str) -> Model:
    """Pydantic AI model for a ``provider:name`` reference, on a shared provider."""
    if reference.startswith("openai:"):
        return OpenAIModel(
            reference.removeprefix("openai:"), provider=provider("openai")
        )
    if reference.startswith("anthropic:"):
        return AnthropicModel(
            reference.removeprefix("anthropic:"), provider=provider("anthropic")
        )
    return infer_model(reference, provider_factory=provider)


def _model_for(spec: ModelSpec) -> Model:
    """Resolve the model and check that it honours the declared reasoning.

    A fake model, when one is installed, replaces the declared one: it calls no
    provider, and the declared reasoning is not checked.

    Raises:
        Unavailable: The provider is unknown or not configured (credentials, URL).
        Unsupported: Reasoning is requested but the adapter would drop it.
    """
    replacement = fake.installed()
    if replacement is not None:
        return replacement
    try:
        model = _resolve_model(spec.model)
    except UserError as exc:
        raise Unavailable(
            f"Model {spec.model!r} cannot be used: check the provider credentials and "
            "base URL in the environment",
            {"model": spec.model, "cause": cause_types(exc)},
        ) from None
    profile = model.profile
    if spec.reasoning is False and profile.get("thinking_always_enabled"):
        # Pydantic AI drops the setting for models that always reason: refuse instead.
        raise Unsupported(
            f"Reasoning cannot be turned off for {spec.model}",
            {"model": spec.model, "option": "reasoning"},
        )
    if spec.reasoning_active and not (
        profile.get("supports_thinking") or profile.get("thinking_always_enabled")
    ):
        # Pydantic AI drops the setting silently for such models: refuse instead.
        raise Unsupported(
            f"The adapter does not apply reasoning to {spec.model}, although the "
            "project declares it",
            {"model": spec.model, "option": "reasoning"},
        )
    return model


def _last_problems(exc: UnexpectedModelBehavior, deps: _Deps) -> list[str]:
    """Problems of the last attempt, from the error that ended the retries.

    A schema failure keeps only the location and the type of each error, not the input
    values; a retry requested by the validator reports its problems. Any other ending
    (for example a final attempt with plain text instead of the output) has no problems
    to report.
    """
    cause = exc.__cause__
    if isinstance(cause, ValidationError):
        return [
            f"{'.'.join(str(item) for item in error['loc'])}: {error['type']}"
            for error in cause.errors(include_url=False, include_input=False)
        ]
    if isinstance(cause, ModelRetry):  # raised by the validator check
        return list(deps.last_problems)
    return []


def _output_failure(
    exc: UnexpectedModelBehavior,
    messages: list[ModelMessage],
    deps: _Deps,
    max_attempts: int,
) -> OutputInvalid:
    """Tell a truncated or filtered response from an output that stayed invalid."""
    last = next((m for m in reversed(messages) if isinstance(m, ModelResponse)), None)
    if isinstance(exc, ContentFilterError):
        return OutputInvalid(
            "The provider filtered the model response", {"reason": "content_filter"}
        )
    if last is not None and last.finish_reason == "length":
        return OutputInvalid(
            "The model response was truncated by the max_tokens limit",
            {"reason": "max_tokens"},
        )
    if isinstance(exc, IncompleteToolCall):
        return OutputInvalid(
            "The model response ended with an incomplete output",
            {"reason": "incomplete_output"},
        )
    return OutputInvalid(
        f"Model output not valid after {max_attempts} attempts",
        {"reason": "invalid_output", "last_problems": _last_problems(exc, deps)},
    )


def _retry_after(exc: ModelHTTPError) -> float | None:
    """Seconds the provider asks to wait before a retry, if it says so."""
    headers = getattr(exc, "headers", None) or {}
    for name, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        value = headers.get(name)
        try:
            seconds = float(value) * scale if value is not None else None
        except ValueError:
            seconds = None  # an HTTP date: the computed wait applies
        if seconds is not None and seconds >= 0:
            return seconds
    return None


async def attempt(request: GenerationRequest, usage: Usage) -> Attempt:
    """One generation, with the attempts of the request for a valid output.

    ``usage`` is updated in place, so the caller keeps the usage of an attempt that is
    cancelled or raises. Provider messages and error bodies are not copied into the
    error: they may contain request data. Cancellation and unexpected exceptions
    propagate.
    """
    guard_sdk_logs()
    retry_after: float | None = None
    deps = _Deps(request.validator)
    error: BreviaError
    with capture_run_messages() as messages:
        try:
            model = _model_for(request.spec)
            settings = settings_for(request.spec, model, request.timeout)
            result = await _AGENT.run(
                request.user_text,
                toolsets=_toolsets(request),
                deps=deps,
                model=ObservedModel(model, request.spec, request.records),
                output_type=_output_function(request.output_type),
                instructions=request.instructions,
                model_settings=settings,
                retries={
                    "output": request.max_attempts - 1,
                    "tools": request.max_attempts - 1,
                },
                usage=usage,
                usage_limits=UsageLimits(
                    request_limit=request.request_limit,
                    tool_calls_limit=request.tool_calls_limit,
                    total_tokens_limit=request.token_limit,
                ),
            )
        except (Unavailable, Unsupported) as exc:
            error = exc
        except UsageLimitExceeded:
            error = LimitExceeded(
                "Run limit reached during generation",
                {
                    "budget": {
                        "requests": request.request_limit,
                        "tool_calls": request.tool_calls_limit,
                        "tokens": request.token_limit,
                    }
                },
            )
        except UnexpectedModelBehavior as exc:
            error = _output_failure(exc, messages, deps, request.max_attempts)
        # The provider exception is not kept as the cause: its message and body may
        # contain request data, which a standard traceback would print.
        except ModelHTTPError as exc:
            status = exc.status_code
            retry_after = _retry_after(exc)
            error = ProviderError(
                f"Model provider error (HTTP {status})",
                {"status_code": status, "cause": cause_types(exc)},
                retryable=(status >= 500 or status in RETRYABLE_HTTP_STATUSES)
                and not (billing_error(request.spec.model.partition(":")[0], exc)),
            )
        except ModelAPIError as exc:
            # No HTTP status: connection problems and timeouts, worth retrying.
            error = ProviderError(
                f"Model provider error: {type(exc).__name__}",
                {"cause": cause_types(exc)},
            )
        else:
            return Attempt(output=result.output)
    return Attempt(error=error, retry_after=retry_after)
