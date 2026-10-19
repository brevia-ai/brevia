# Logging

Read this page to send the records of Brevia to the logs of the application and to
know what they contain.

Brevia uses the standard `logging` module, with one logger per module under the
`brevia` namespace. The library emits records and never configures logging by itself:
the application does.

The simplest set-up is a call at start-up:

```python
from brevia import BreviaSettings, configure_logging

settings = BreviaSettings()
configure_logging(settings.log_level, settings.log_format)
```

`configure_logging` replaces the handlers of the root logger with one that writes to
the standard error, as readable text (`text`, for development) or one JSON object per
line (`json`, for production). Applications with their own logging set-up can skip it.

## What is logged

- Start, success, failure and cancellation of each run, with its duration, the paths
  of the overrides, the number of model requests and the estimated cost.
- Each model call, with the model, requests, tokens, duration and error code if any,
  also when the call is cancelled or fails unexpectedly.
- Unexpected failures, once, where they are handled: the exception type and the stack
  frames, without the exception message, which may contain data from dependencies.

Records about a run carry the `run_id` and `activity` attributes, which the JSON format
includes, so that the events of one run can be correlated. The records of the requests
of the [HTTP API](http-api.md) that fail with a server error (`5xx`) carry
`request_id`, the identifier also returned in the `X-Request-ID` header and in the
error body; the text format shows it as `[request ...]`, as it shows `[run ...]`. The
records of the runs and jobs that a request starts do not carry it.

Logs never contain credentials, tokens, document contents, or full prompts and
responses. At the `DEBUG` level, which also applies to the libraries Brevia uses, the
Anthropic SDK would log the options of each request with its body: Brevia drops those
records (logger `anthropic._base_client`, filtered from the first model request). Other loggers of dependencies are not filtered: keep `DEBUG` for local
diagnosis, not for production. The contents of model calls are recorded apart from the logs, in the
database, only with `capture="full"` (see
[Contents of model calls](runs.md#contents-of-model-calls) and
[Data retention](runs.md#data-retention)).

## Records of the job engine

The engine that runs jobs (DBOS) logs to the `dbos` logger. When Brevia starts its job
backend or a worker, the records of that logger go to the handlers of the application,
as those of Brevia, instead of a console handler of their own, and they are filtered:

- debug records are dropped;
- a message stops before its first `": "`, after which the engine writes the text of an
  exception, a value or a database URL;
- an exception is reduced to its type, without its message, chain or stack frames.

With the messages of the engine as they are in DBOS 3.2, the messages of database
drivers (host, user, database) and the values of a job do not reach the logs in this
way; the filter relies on that form, so a new version of the engine is checked
against it. The lines of the engine are less detailed as a
consequence: the message and the type of the exception tell what failed, not why.

## Levels

| Level | Meaning |
|---|---|
| `DEBUG` | Diagnosis |
| `INFO` | Significant events, such as runs and model calls |
| `WARNING` | Recoverable problems, and runs that failed with a Brevia error |
| `ERROR` | Failed operations, such as unexpected errors |
