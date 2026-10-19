# Models and limits

Read this page to choose and declare the models of a project, to obtain a validated
structured output from them, and to understand what stops a run that spends too much.

## Model references

A model is referenced as `provider:name`, for example `openai:gpt-6-luna`,
`anthropic:claude-sonnet-5-5` or `ollama:llama3.3`. The supported providers are
`openai`, `anthropic` and `ollama`; other prefixes are rejected when the project file is
loaded. Credentials and endpoints come from the environment variables of each provider
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_BASE_URL`): if they are missing, a
generation fails with `Unavailable`.

An activity configuration selects the model with a `model` field, which holds either a
reference or a full model use:

```python
from pydantic import BaseModel

from brevia import ModelSpec


class Config(BaseModel):
    model: str  # "openai:gpt-6-luna"


class DetailedConfig(BaseModel):
    model: ModelSpec  # model, reasoning, temperature, max_tokens
```

A `ModelSpec` field also accepts a reference alone, as `model = "openai:gpt-6-luna"` in
the project file: it stands for that model with the default options. With a
`ModelSpec` field, a customisation or an override may change one option and keep the
others, for example `{"model": {"reasoning": "high"}}` when `model.reasoning` is
overridable; with a `str` field the model can only be replaced as a whole. A string
given to a `ModelSpec` field replaces the whole model use too, so its options return
to their defaults. In Python
code, build it as `ModelSpec(model="openai:gpt-6-luna")`.

`ctx.model()` returns the client of that model. `ctx.model(override)` adjusts the model
use for one step, for example `ctx.model({"reasoning": "high"})`; the overrides of the
request still prevail.

## Declared capabilities

The project file declares every model the project may use:

```toml
[models."openai:gpt-6-luna"]
reasoning_levels = ["low", "medium", "high", "xhigh", "max"]
temperature = true
temperature_with_reasoning = false
prices = { input = 0.10, cached_input = 0.01, output = 0.50 }
```

Capabilities and prices come from the page of the model of the provider (for
`gpt-6-luna`, prices of October 2026 in USD per million tokens). Brevia does not
read them from the provider: update the project file when they change.

| Field | Meaning |
|---|---|
| `reasoning_levels` | Reasoning levels the model accepts: `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, as listed by the provider for that model. Empty if reasoning cannot be controlled. `reasoning = false` (`none` for OpenAI) needs no level. |
| `temperature` | Whether the model accepts a temperature. |
| `temperature_with_reasoning` | Whether a temperature is accepted while reasoning is on. |
| `prices` | USD per million tokens, used to estimate costs. Optional. |

A model that is not declared cannot be used (`Unsupported`), and an option outside the
declared capabilities is refused before any request (`Unsupported`). Capabilities are
never inferred from the model name. The adapter may refuse a reasoning option even
when the project declares it: see [Advanced notes](#advanced-notes).

## Structured generation

`generate` asks the model for an output of a given type, validates it and sends the
problems back to the model until the output is valid or the attempts are over. In
this example the output is a Pydantic model and a validator adds a check that the
schema cannot express (`SummaryRequest` and `SummaryConfig` are those of
[Getting started](../getting-started.md)):

```python
from pydantic import BaseModel

from brevia import RunContext


class Result(BaseModel):
    summary: str
    key_points: list[str]


def check_result(result: Result) -> list[str]:
    """Problems of a valid Result; an empty list accepts it."""
    problems = []
    if len(result.key_points) > 5:
        problems.append("Give at most 5 key points.")
    if len(result.summary) > 1500:
        problems.append("Keep the summary under 1500 characters.")
    return problems


async def summarize(request: SummaryRequest, ctx: RunContext[SummaryConfig]) -> Result:
    result = await ctx.model().generate(
        instructions=ctx.prompt("summary").render(language=ctx.config.language),
        user_text=request.text,
        output_type=Result,
        validator=check_result,  # optional
        max_attempts=3,  # default
        max_output_tokens=1200,  # optional, replaces max_tokens of the model use
    )
    return result
```

1. The output is validated against `output_type`.
2. A valid output is passed to the `validator`, a function that receives it and
   returns a list of problems as text; an empty list accepts it.
3. Schema errors and validator problems are sent back to the model as a retry, up to
   `max_attempts` attempts in total.

The result has the type given as `output_type`, for type checkers too, when it is a
class or a parametrised generic (a Pydantic model, a TypedDict, `list[str]`). For other
type forms see [Advanced notes](#advanced-notes).

If no valid output is obtained, `OutputInvalid` is raised; its `details["reason"]`
tells why:

| Reason | Meaning | What to do |
|---|---|---|
| `invalid_output` | The attempts ended without a valid output. `last_problems` lists the problems of the last attempt: the validator messages, or the location and type of each schema error (never the values). | Make the instructions or the schema clearer, or raise `max_attempts`. |
| `max_tokens` | The response was truncated by the `max_tokens` limit. | Raise the limit; retrying as it is will not help. |
| `content_filter` | The provider filtered the response. | Check the input; retrying the same request will usually fail again. |
| `incomplete_output` | The response ended with an incomplete output. | Retry, or raise the output limit. |

## Run limits

Limits apply to a whole run, failed attempts included. `0` turns a limit off:

| Limit | Default | Applies to |
|---|---|---|
| `max_requests` | 20 | Model requests, retries included |
| `max_tool_calls` | 0 (off) | Tool calls |
| `max_total_tokens` | 0 (off) | Input and output tokens |
| `max_seconds` | 900 | Duration of the run, in seconds |
| `provider_retries` | 2 | Retries of a request after a temporary provider error |

The two limits on by default are guards against errors rather than budgets: a model
that keeps calling a tool stops at `max_requests`, and a run waiting for a provider
that does not answer stops at `max_seconds`. Token and tool call limits are choices of
the project.

The project sets them in its `[limits]` table, and an activity may set its own at
registration. Usage exactly at a limit is accepted. The limits work in three different
ways, because some usage is known before a call and some only after its answer.

### Requests: reserved when a call starts

Each model call reserves `max_attempts + provider_retries` requests when it starts, so
that concurrent calls in the same run cannot exceed `max_requests` together, and
retries after provider errors do not take the attempts for a valid output. A call
with tools also reserves one request per tool call allowed by `max_tool_calls`, or
every request left in the run when tool calls have no limit, since every turn with
tools is a request: a sequence of tool calls is limited by the
requests and tool calls of the run, not by the attempts. When the call ends, the
requests it did not use return to the run.

With the defaults, each call reserves 3 + 2 = 5 requests of the 20 of the run:

| Concurrent call | Requests left before it | Outcome |
|---|---|---|
| 1st | 20 | Reserves 5 |
| 2nd | 15 | Reserves 5 |
| 3rd | 10 | Reserves 5 |
| 4th | 5 | Reserves 5 |
| 5th, started while the others run | 0 | Refused at once with `LimitExceeded` |

A call with tools usually takes all the requests left, so calls with tools are
better made one after the other. A call may therefore be refused while other calls
hold reservations they will not use in full. A call that finds fewer requests left than its reservation runs with those
left. An activity that runs more calls concurrently increases `max_requests`, or
lowers `max_attempts` for each call. Calls made one after the other are not affected:
each finds the requests the earlier calls did not use.

### Duration: a deadline for the whole run

`max_seconds` covers the whole activity, model calls and other work alike. An exceeded
duration raises `RunTimeout`. Each model call receives the time left as its timeout,
and a deadline passed during a call is a `RunTimeout` whatever the outcome of the call.
The deadline interrupts asynchronous waits; blocking code that never yields to the
event loop cannot be interrupted, and the run fails with `RunTimeout` when it returns
late. For a job, the deadline counts from its first start (see
[Jobs](jobs.md#values-fixed-when-the-job-starts)).

### Tokens and tool calls: known only after the answer

Tokens are known only after each response, so they cannot be reserved: each call
receives the tokens left when it starts, and a limit is not an exact cap on tokens or
cost.

- A call that goes over the tokens left raises `LimitExceeded`; using exactly the
  tokens left is allowed. A call that starts with no tokens left raises it at once.
- Concurrent calls may together go over the token or tool call limit. Once their usage
  is known, each call that finishes while the run is over the limit raises
  `LimitExceeded` and its output is discarded, while its usage stays counted.
- A call that fails with its own error keeps that error.
- The run fails even if the activity caught the `LimitExceeded`: the totals are
  checked again when the activity returns.
- A call that is cancelled or fails unexpectedly still counts the requests and tokens
  it used.

## Usage and cost

Each run accumulates the requests, tool calls and token counters of every model call,
including cache reads and writes, and an estimated cost from the declared prices. The
cost is *unknown* (`None`) as soon as one call lacks a needed price, or a request of
the call may have been billed without reporting its usage (an answer without usage, a
cancellation, a timeout or a lost connection): a partial sum would understate it. An
error answer of the provider, such as a rate limit followed by a retry, generates
nothing to bill and leaves the cost known. Costs are estimates, not invoices.

## Output tokens and reasoning

`max_tokens` bounds what each request may generate. By default it is not set and
nothing is sent: OpenAI and Ollama apply the maximum of the model, and for Anthropic,
whose API requires a value, Pydantic AI sends the maximum of the model (128,000 tokens
for the Claude 5.5 models) and receives the response as a stream behind the scenes
(see [Anthropic](#anthropic)). A project sets it
to bound the length, and the cost, of each response. For reasoning
models it includes the reasoning tokens, not only the visible answer: a request that
reaches it may end before any answer, after the input and the reasoning are billed.
Brevia stops at such a response, without other attempts, with `output_invalid` and
`reason` `max_tokens`. OpenAI suggests leaving at least 25,000 tokens to reasoning and
answer when trying a reasoning model; lower `max_tokens` only after measuring the
`reasoning_tokens` of the requests of the project (see [Recorded runs](runs.md)).

| `reasoning` in the model use | OpenAI | Anthropic | Ollama |
|---|---|---|---|
| not set | nothing: the default of the model (often `medium`) | nothing: the default of the model (`high`, `medium` on Opus 5.5 and Haiku 5.5) | nothing |
| `true` | `medium` | reasoning on, with the default effort | reasoning on, if the adapter supports it for the model |
| `false` | `none` (not available on every model) | thinking off; refused on models that always reason (Opus 5.5, Sonnet 5.5) | reasoning off |
| a level, for example `"high"` | that level | that effort; `xhigh` only on models that support it | that level, if the adapter supports reasoning for the model |
| `"max"` | `max` | effort `max` | refused |

Brevia never replaces a requested option with another one: what an adapter cannot
apply is refused with `unsupported` before any request, also when Pydantic AI would
drop it silently (reasoning on Ollama models whose profile has no reasoning, `false` on
Claude models that always reason, a temperature on Claude models that refuse it).
LiteLLM takes the same default and drops parameters only with `drop_params`. A
temperature together with active reasoning is refused when the model does not accept
it. Equal level names do not promise equal budgets across providers.

## Providers

| | OpenAI | Anthropic | Ollama |
|---|---|---|---|
| API | Responses | Messages | Chat Completions of Ollama |
| Responses stored by the provider | not stored for later use (`store: false`); other retention, such as abuse monitoring, follows the data policy of the account | as the data policy of the account | none: local |
| Errors not retried among the 429 | billing codes (below) | the monthly spend cap (`enforced_spend_limit_reached`) | — |
| Other billing errors | — | 402 `billing_error`; a spend limit set by the organization is a 400 | — |
| Identifier of the request in the records | `x-request-id` | `request-id` | — |
| Requests that may take long | the time left of the run is the timeout of each request | the same; streamed behind the scenes only without a `max_tokens` (below) | the same |

### OpenAI

- Brevia uses the Responses API and sends `store: false`: OpenAI does not store the
  responses for later retrieval, so they do not appear in its dashboard. This is not
  Zero Data Retention: other retention, such as the logs kept for abuse monitoring,
  follows the data policy of the account. The reasoning of a request is
  returned encrypted and sent back by the adapter, so turns with tools work without
  stored state.
- Rate limits (`rate_limit_error`, `slow_down`) are retried as below. Billing errors
  (`credit_balance_exhausted`, `organization_spend_limit_exceeded`,
  `project_spend_limit_exceeded`, `organization_usage_limit_exceeded`, and
  `insufficient_quota`) are not: repeating them does not restore access, so the call
  fails at once with a `ProviderError` that is not retryable.

### Anthropic

- A 429 is a rate limit, or the monthly spend cap of the tier of the account, which
  has no `retry-after` and fails until the next month: Brevia recognises the cap by
  its `error_code` and does not retry it. A 402 (`billing_error`) is not retried
  either.
- `max_tokens` includes the thinking. Anthropic suggests large values at the higher
  efforts, and streaming for requests that may take more than 10 minutes, since some
  networks drop idle connections. Without a `max_tokens` in the model use, Pydantic AI
  asks for the maximum of the model and, when it is above 21,333 tokens (as for the
  Claude 5.5 models), receives the response as a stream; Brevia still returns the
  whole validated output at the end. With a `max_tokens` set by the project, the
  request is sent whole, with the time left of the run as its timeout: the SDK does
  not refuse a large value, but a very long request may be dropped by the network.

## Temporary provider errors

Brevia retries a model request that fails with a temporary provider error: rate
limits (429, except the billing errors of [OpenAI](#openai)), timeouts (408), conflicts
(409), server errors (5xx) and connection problems. Other errors, such as an invalid request (400) or missing credentials, are not
retried.

- A request is retried at most `provider_retries` times (2 by default, `0` disables
  retries), in the `[limits]` table of the project or the limits of an activity.
- The waits double from about one second, with some randomness, up to 30 seconds.
  When the provider says how long to wait, as a number of seconds in `Retry-After` or
  of milliseconds in `retry-after-ms`, Brevia waits at least that long, up to 120
  seconds: a provider asking for a longer wait is not retried. A `Retry-After` given
  as an HTTP date is ignored, and the computed wait applies.
- A retry is not attempted when its wait would leave less than a second of the run:
  the call fails with the `ProviderError` of the last attempt.
- Each failed request counts as a request of the run, and retries stay within the
  [reserved requests](#requests-reserved-when-a-call-starts): when no request is left
  for a retry, the call fails with the `ProviderError` of the last attempt. Usage and
  recorded requests include the failed ones, since a provider may bill them.
- Retries for an invalid output are separate: they are the attempts of `max_attempts`
  (see [Structured generation](#structured-generation)). An error after the model has
  already answered in the call, for example after an invalid output, is not retried:
  a retry would start the attempts again, beyond `max_attempts` and without the
  feedback given to the model.

## Advanced notes

- **Type forms as `output_type`.** Unions, `Annotated` and `Literal` are accepted at
  run time, but type checkers refuse them as `output_type` until type forms can be
  annotated (PEP 747): use `cast` or a `type: ignore[arg-type]` comment there.
- **Reasoning and the adapter.** The model adapter applies a reasoning setting only to
  models it knows to support reasoning, and would otherwise drop it without notice.
  Brevia checks this too: a request with reasoning on a model whose adapter would
  ignore it fails with `Unsupported`, even when the project declares the levels. In
  the same way, `reasoning = false` fails with `Unsupported` on a model that always
  reasons, where the adapter would drop it.
- **Provider clients.** Each provider has one client per event loop, created at the
  first call and reused by the following calls on that loop; the clients are closed
  when the last started `Brevia` stops. The libraries of the providers do not retry by
  themselves: their retries are turned off, so that no retry happens outside the
  limits.
- **Token counters.** Token counters come from the model adapter. When a provider does
  not report a counter, the adapter reports zero, so "not reported" cannot yet be told
  apart from zero.
- **A response over the tokens left.** A call whose response goes over the tokens left
  counts its tokens but not its request, so `max_requests` and the recorded usage may
  understate by one request.

## Runnable examples

See [the executable analysis example](analysis-example.md) for a complete application with a fake model. Model-selected file operations are described in [Tools](tools.md).
