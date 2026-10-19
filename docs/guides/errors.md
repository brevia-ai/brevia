# Errors

Read this page when a Brevia call raises an error or a run fails, to know what the
error means and what to do next.

Every error raised by Brevia derives from `BreviaError` and has a stable `code`, a
`message`, `details` and a `retryable` flag; `to_dict()` returns them as
`{code, message, details, retryable}`. Messages and details never contain secrets or
document contents. Each class also has the `http_status` the HTTP API uses, given below.

```python
from brevia import BreviaError, VersionConflict

try:
    await brevia.customize_configuration(
        "document.summarize", {"language": "fr"}, expected_version=3
    )
except VersionConflict as exc:
    print(exc.code, exc.details)  # version_conflict {...expected and current...}
except BreviaError as exc:
    if exc.retryable:
        ...  # repeating the same operation later may succeed
    raise
```

## Retryable errors

`retryable` says whether repeating the same operation, unchanged, may succeed. Each
class has a default, and some errors set it themselves:

| Error | `retryable` |
|---|---|
| `Unavailable` | `True` |
| `ProviderError` | `True` for connection problems, timeouts and HTTP 408, 409, 429 and 5xx statuses; `False` for other client errors such as 400, 401 or 404 |
| `Unsupported` for a job whose activity changed version before it started | `True` |
| `InternalError` for a job interrupted by a release, or ended by the engine without recording its outcome | `True` |
| Every other error | `False` |

A `ProviderError` is raised after Brevia has retried the request at most
`provider_retries` times. It may stop earlier: when the error is not temporary, when
the wait would leave no time to the run, when no request is left for a retry, or when
the model had already answered in the same attempt (see
[Temporary provider errors](models.md#temporary-provider-errors)). A retryable one is
worth repeating later, not at once. For a [job](jobs.md#retry), the
repetition is `handle.retry()`, which submits a new job with the same input and
overrides. A `False` flag means that the same request will fail again: change it first.

## Errors of an operation

| Class | Code | HTTP | When | What to do |
|---|---|---|---|---|
| `InvalidInput` | `invalid_input` | 422 | Input, override, customisation or model option not valid; a file source not allowed (host, extension, local path from a caller), refused by its server or different from its declared size or fingerprint | Fix the value: the details give the location and type of each problem, or the name of the file |
| `OverrideNotAllowed` | `override_not_allowed` | 422 | Override of a path the activity does not declare in `overridable` | Remove the paths listed in the details, or declare them in the activity |
| `NotFound` | `not_found` | 404 | Activity, prompt, job, output file or local input file missing, or a job the caller may not see | Check the name or the job identifier |
| `IdempotencyConflict` | `idempotency_conflict` | 409 | A job or feedback submitted with a used idempotency key and a different request (for feedback, also a different end user) | Send the same request with that key, or use a new key for a new request |
| `VersionConflict` | `version_conflict` | 412 | `expected_version` of a configuration or prompt change is no longer current | Read the state again, decide whether the change still applies, and repeat it with the new version |
| `NotReady` | `not_ready` | 409 | `result` of a job that has not ended (within `wait`) | Keep the job identifier and call `result` again later; the job goes on |
| `Busy` | `busy` | 409 | `retry` of a job that has not ended | Wait for the job to end, or cancel it, then retry |
| `Unsupported` | `unsupported` | 422 | File format not readable, model not declared, option outside the declared capabilities, `retry` of a job that succeeded, or a job whose activity changed version | Change the model or the option, or declare the capability; for a retryable one, retry the job |
| `ProviderError` | `provider_error` | 502 | Error of the model provider | If retryable, repeat later; otherwise fix the request or the credentials |
| `Unavailable` | `unavailable` | 503 | Database not reachable, schema not migrated, provider configuration or credentials missing, project file or stored customisation not valid, files not configured, or the server of an input file failing or unreachable | Fix the cause given in the message and details, then repeat |
| `Unauthorized` | `unauthorized` | 401 | Missing or invalid token | Send a valid token; see [Callers and tokens](access.md#authentication) |
| `Forbidden` | `forbidden` | 403 | The access policy denies the operation | Ask as an administrator; see [Access](access.md#access-to-runs-and-customisations) |
| `FileTooLarge` | `file_too_large` | 413 | File larger than allowed | Use a smaller file, or raise `BREVIA_FILES_MAX_BYTES`; see [Files](files.md#input-files) |

## Run failures

A failed run reports `{code, message, details, retryable}`. A direct run raises the
error, with the `run_id` of the run in `details`; a job records it and `result` raises
it. Over HTTP a failed direct run answers with the status of the table and a failed
job answers `409` to `GET /runs/{run_id}/result`: never a `5xx`, except `internal`,
since clients and proxies repeat `5xx` answers by themselves and every repetition would
call the model again.

| Class | Code | HTTP | When | What to do |
|---|---|---|---|---|
| `LimitExceeded` | `limit_exceeded` | 422 | A request, token or tool call limit was reached (see [Run limits](models.md#run-limits)) | Raise the limit, or reduce the work of the run; repeating it unchanged reaches the limit again |
| `RunTimeout` | `timeout` | 422 | The run exceeded `max_seconds` | Raise `max_seconds`, or reduce the work of the run |
| `OutputInvalid` | `output_invalid` | 422 | No valid output within `max_attempts` | Depends on `details["reason"]`: see [Structured generation](models.md#structured-generation) |
| `ToolError` | `tool_error` | 422 | A tool failed | Not raised by Brevia: a failing tool stops the run with its own error (`internal_error` for an exception that is not a Brevia error); a tool of the application may raise it for its own failures |
| `Cancelled` | `cancelled` | 422 | The run was cancelled | Retry the job if it is still needed |
| `InternalError` | `internal` | 500 | An unexpected exception in the activity, or a job interrupted by a release | Read the log records of the run (`run_id`) for the type and the stack frames; retry when retryable |

A run also fails with any error of the previous table raised during it, for example
`invalid_input` for a configuration or model option refused, `unsupported` for a
capability not offered, `provider_error` or `unavailable`.

## What errors never contain

Error details are meant to be logged and returned to callers, so they leave out
anything that may contain request data or credentials:

- A `ProviderError` lists in `details["cause"]` the type names of the chain of causes,
  for example `["ModelAPIError", "APIConnectionError", "LocalProtocolError"]`: enough to
  tell a connection problem from a rejected request. The original exception is not
  kept as its cause either: its message and the response body may contain request
  data, and a standard traceback, as printed by `logging.exception()`, would show them.
- An `InvalidInput` for a request that does not match the input schema, or for invalid
  overrides or model options, lists the location and type of each problem, never the
  values. The Pydantic error is not kept as its cause, since its message quotes the
  values.
- An unexpected exception inside an activity becomes an `InternalError` that names
  only the exception type: messages of dependencies may contain data or secrets. The
  original exception is neither its cause nor its context, also when recording the
  failure fails and an `Unavailable` replaces it, so that a standard traceback of the
  caller does not print its message. The log records its type and its stack frames,
  but not its message.
