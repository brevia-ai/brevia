# HTTP API

Brevia serves its operations over HTTP with [FastAPI](https://fastapi.tiangolo.com/).
The API is a thin layer: every endpoint calls an operation of
[`Brevia`](../reference/application.md#brevia.Brevia) that Python code can call too.

## The application

[`create_app`](../reference/api.md#brevia.api.create_app) builds the HTTP application
around the `Brevia` of the project, with its activities registered:

```python
# myproject/api.py
from brevia import Brevia, BreviaSettings, configure_logging
from brevia.api import BreviaDep, CallerDep, create_app

settings = BreviaSettings()
configure_logging(settings.log_level, settings.log_format)
brevia = Brevia.from_settings(settings)
brevia.register_activity(...)  # the activities of the project

app = create_app(brevia)


@app.post("/documents", status_code=202)  # an endpoint of the application
async def create_document(
    request: DocumentRequest, brevia: BreviaDep, caller: CallerDep
) -> dict[str, str]:
    handle = await brevia.submit("document.generate", request, caller=caller)
    return {"run_id": handle.run_id}
```

An endpoint of the application receives the Brevia of the app with
[`BreviaDep`](../reference/api.md#brevia.api.BreviaDep) and the caller of the request
with [`CallerDep`](../reference/api.md#brevia.api.CallerDep): a request without a valid
token is refused with `401` before the endpoint runs, and its errors get the same body
as those of Brevia. The [project template](project-template.md) has a complete
example.

```sh
uv run --env-file .env uvicorn myproject.api:app
```

In production expose the API only over HTTPS: the token of every request travels in
its `Authorization` header. As with Brevia 0.15, the application serves HTTP and the
installation adds TLS in front of it, with a reverse proxy or the gateway of the
platform (or uvicorn itself, with `--ssl-keyfile` and `--ssl-certfile`).

The app does three things for every project, so that none of them can be forgotten:

- **Start and stop.** It starts Brevia when it starts (database connection, schema
  check) and stops it when it stops. If the database cannot be reached, the server does
  not start.
- **The caller of each request.** An endpoint that needs it reads the
  `Authorization: Bearer <token>` header and gets the
  [caller](access.md#the-caller-of-an-operation) of the token, which every operation
  receives: the [access policy](access.md) decides what it may see and do. A backend
  that acts for one of its users names it in the `end_user` field of the body of a
  run, a feedback or a change: it becomes the
  [end user](access.md#the-caller-of-an-operation) of the caller, recorded with the
  run, the job, the feedback or the customisation, and grants no permission. Send an
  opaque value, such as an id or a hash, never a name or an email address. A blank
  value, one longer than 200 characters or one with a NUL character gives
  `422 invalid_input`, without the value in the answer.
- **One error body.** Every error has the same JSON body and the HTTP status of its
  [error class](errors.md):

```json
{
  "code": "not_found",
  "message": "Job not found",
  "details": {"run_id": "..."},
  "request_id": "2b0c6a3e-..."
}
```

`request_id` is generated for every request and returned in the `X-Request-ID`
header of every response; the log records of a request that fails with a server
error (`5xx`) carry it, so that a caller can report it. A request that does not match
the schema of an endpoint gives `422 invalid_input`, with the location and the message
of each problem but not the values sent. An unexpected error gives `500 internal`: its
message is not returned and only its type is logged.

| Parameter of `create_app` | Default | Meaning |
|---|---|---|
| `settings` | read from `BREVIA_*` and `.env` | Authentication settings: token secret, accepted callers, status token ([settings](access.md#settings)) |
| `docs` | `True` | Serve `/docs`, `/redoc` and `/openapi.json`; `False` hides them, for example in production |

Without a token secret, and without `BREVIA_AUTH_DISABLED=true`, `create_app` raises
`ValueError`: the API never starts open by mistake.

The OpenAPI document at `/openapi.json` describes the error answers with the error
body above (`ErrorBody`), except those an endpoint of the application declares with a
schema of its own, and every endpoint that needs a token with the Bearer scheme,
so that a client generated from it reads the errors correctly. In `/docs`, the
**Authorize** button takes a token (`brevia token create`) and sends it with the
requests tried from the page. Its version is the version of Brevia.

## Activities and runs

Every endpoint below needs a token: the caller of the token is passed to the
operation, and the [access policy](access.md) decides what it may see. Under the
default `per-caller` policy, a job of another caller is not found (`404`), as one that
does not exist.

| Endpoint | Python operation | Answer |
|---|---|---|
| `GET /activities` | `Brevia.activities` | `200`, the registered activities by name: `name`, `version`, `modes` |
| `GET /activities/{name}` | `Brevia.activities` | `200`, also `overridable` and the JSON schemas `input_schema` and `output_schema`; `404` if not registered |
| `POST /runs` | `Brevia.run` or `Brevia.submit` | direct: `200` with `run_id`, `status` and `output`; job: `202` with the state of the job and a `Location` header |
| `GET /runs` | `Brevia.jobs` | `200`, a page of jobs, newest first: `{"jobs": [...], "next_cursor": ...}` |
| `GET /runs/{run_id}` | `RunHandle.status` | `200`, the state of the job |
| `GET /runs/{run_id}/result` | `RunHandle.result` | `200` with the output; `409` if the job has not ended or did not succeed |
| `POST /runs/{run_id}/cancel` | `RunHandle.cancel` | `200`, the state of the job; calling it again does nothing |
| `POST /runs/{run_id}/retry` | `RunHandle.retry` | `202`, the state of the new job and its `Location`; `409 busy` if the job has not ended, `422 unsupported` if it succeeded |
| `POST /runs/{run_id}/feedback` | `Brevia.add_feedback` | `201`, the [feedback](runs.md#feedback) as recorded; `404` if the run is not recorded or not the caller's |
| `GET /runs/{run_id}/files/{name}` | `RunHandle.file` | `200` with the content of an output file of the job; `404` if there is no such file |

The body of `POST /runs`:

```json
{
  "activity": "document.summarize",
  "input": {"text": "..."},
  "overrides": {"language": "en"},
  "mode": "job",
  "end_user": "user-42"
}
```

Outputs are returned as JSON with the aliases of their fields and their computed
fields, as `output_schema` describes them; `input_schema` describes the input as it is
validated.

`overrides` and `end_user` are optional; `overrides` accepts only the paths listed in
`overridable`. `mode` is
`direct` or `job`; it may be omitted when the activity supports one mode only, and
is required otherwise (`422 invalid_input`). Fields not listed here are refused, so
that a misspelt field is not ignored.

### Direct runs

A direct run answers when the activity ends, with its identifier and its output:

```json
{"run_id": "1d6f…", "status": "succeeded", "output": {"summary": "..."}}
```

`run_id` is the identifier of the run in the logs and in the database, where its usage
and model calls are recorded: send [feedback](#feedback) to it. A run that fails
answers with the error body of its error and its `run_id` in `details`; a failure of
the run itself (`output_invalid`, `limit_exceeded`, `timeout`, `cancelled`) answers
`422`, not a server error, so that clients and proxies do not repeat it by themselves. When the installation does
not record direct runs, `run_id` still names the run in the logs, but feedback on it
answers `404`.

### Jobs

A job answers at once: the request records and queues it, and a
[worker](workers.md) runs it. The request never waits for the job to end.

```text
POST /runs                    -> 202 {"run_id": "6f1c…", "status": "queued", ...}
GET  /runs/6f1c…              -> 200 {"status": "running", ...}
GET  /runs/6f1c…              -> 200 {"status": "succeeded", "usage": {...}, ...}
GET  /runs/6f1c…/result       -> 200 {"summary": "..."}
```

The state of a job has the fields of [`JobState`](../reference/runs.md): `run_id`,
`activity`, `activity_version`, `status` (`queued`, `running`, `succeeded`, `failed`,
`cancelled`), `created_at`, `started_at`, `finished_at`, `error`, `usage` and
`retry_of`.

With an `Idempotency-Key` header, submitting the same request again gives back the same
job, in any status, with `202`; the same key with a different request gives
`409 idempotency_conflict`. The key is scoped to the activity and to the caller, as in
[`submit`](jobs.md#idempotency). A direct run refuses the header (`422 invalid_input`): it has
nothing to give back. `POST /runs/{run_id}/retry` accepts the header too.

### Listing jobs

`GET /runs` lists the jobs the caller may see, newest first, as
[`Brevia.jobs`](jobs.md#listing-jobs) does. The query parameters `activity`, `status`
and `idempotency_key` filter the list; `limit` is from 1 to 100 (default 20). For the
next page, send `next_cursor` as `cursor` with the same filters:

```text
GET /runs?status=failed&limit=2            -> 200 {"jobs": [{...}, {...}], "next_cursor": "MjAyNi0x…"}
GET /runs?status=failed&limit=2&cursor=MjAyNi0x…  -> 200 {"jobs": [{...}], "next_cursor": null}
```

A caller that lost the `run_id` of a job finds it from its key, without submitting the
job again: `GET /runs?activity=document.summarize&idempotency_key=doc-1`.

### Feedback

`POST /runs/{run_id}/feedback` adds [feedback](runs.md#feedback) to a recorded run,
direct or job, with the fields of `Brevia.add_feedback` and the optional `end_user`:

```json
{
  "kind": "correction",
  "items": [{"target": "summary", "original": "Revenue grew.", "corrected": "Revenue grew by 4%."}],
  "external_ref": {"system": "bedita", "object_id": "42", "revision": "3"},
  "end_user": "user-42"
}
```

It answers `201` with the feedback as recorded, with its `id`, `source`, `caller`,
`end_user` and `created_at`. Feedback that does not match its kind gives
`422 invalid_input`. With an `Idempotency-Key` header, sending the same feedback again
answers `201` with the feedback already recorded, and different feedback with the same
key gives `409 idempotency_conflict`.

### Results

`GET /runs/{run_id}/result` of a job that has not ended answers
`409 not_ready`, with `run_id` and `status` in the details. A job that failed or was
cancelled answers `409` with the code, the message and the details of its error, plus
`run_id` and `retryable`:

```json
{
  "code": "output_invalid",
  "message": "The output is not valid",
  "details": {"attempts": 2, "run_id": "6f1c…", "retryable": false},
  "request_id": "2b0c6a3e-..."
}
```

The status is `409` whatever the error of the job: reading the result succeeded, the
job did not. A `502` for a job that failed on its provider would look like a failure
of the API, and clients and proxies repeat `5xx` answers by themselves.

`GET /runs/{run_id}` and the endpoints below it, except feedback, are for jobs only:
a direct run gives its output in the answer of `POST /runs`; afterwards it can only
receive feedback. In an application without activities that support jobs, `GET /runs`
answers `200` with an empty page and the endpoints of a single job answer `404`;
feedback is accepted on recorded direct runs.

## Configuration and prompts

The customisations of the [configuration](configuration.md#customisation) and of the
[prompts](prompts.md#customisation) of each activity, keyed by the name of the
activity. Every caller with a token reads them; under the `per-caller` policy only the
[administrators](access.md#access-to-runs-and-customisations) change them, others get
`403 forbidden`.

| Endpoint | Python operation | Answer |
|---|---|---|
| `GET /configurations` | `Brevia.configuration` | `200`, the configuration of every activity |
| `GET /configurations/{activity}` | `Brevia.configuration` | `200`, [`ConfigurationState`](../reference/customization.md): defaults, customisation, effective values, customisable paths, schema, version |
| `PATCH /configurations/{activity}` | `Brevia.customize_configuration` | `200`, the new state |
| `POST /configurations/{activity}/reset` | `Brevia.reset_configuration` | `200`, the new state |
| `GET /prompts` | `Brevia.prompt` | `200`, every prompt of every activity |
| `GET /prompts/{activity}/{name}` | `Brevia.prompt` | `200`, [`PromptState`](../reference/customization.md): file text, customisation, effective text, variables, version |
| `GET /prompts/{activity}/{name}/revisions` | `Brevia.prompt_history` | `200`, the changes, most recent first |
| `PUT /prompts/{activity}/{name}` | `Brevia.customize_prompt` | `200`, the new state |
| `POST /prompts/{activity}/{name}/reset` | `Brevia.reset_prompt` | `200`, the new state |

The bodies of the changes:

```text
PATCH /configurations/document.summarize    {"values": {"max_output_tokens": 1800}, "expected_version": 3, "end_user": "user-42"}
POST  /configurations/document.summarize/reset   {"fields": ["max_output_tokens"], "expected_version": 4}
PUT   /prompts/document.summarize/summary    {"text": "Summarise in {language}.", "expected_version": 1}
POST  /prompts/document.summarize/summary/reset  {"expected_version": 2}
```

`expected_version` is optional: when given, a change made meanwhile by someone else
refuses this one with `412 version_conflict` (see
[concurrent changes](configuration.md#concurrent-changes)); read the state again and
repeat. Without `fields`, a reset returns the whole configuration to the defaults.
To restore an earlier prompt, send the `text` of its revision with `PUT`. The author
recorded with a change is its `end_user`, or the caller itself. A change applies to the runs and the jobs that start after it.

## Health

| Endpoint | Token | Answer |
|---|---|---|
| `GET /health/live` | none | `200 {"status": "ok"}` while the process answers |
| `GET /health/ready` | none | `200 {"status": "ready"}` when Brevia is started and its database answers with the migrated schema; otherwise `503 {"status": "unavailable"}` |
| `GET /status`, `HEAD /status` | the token of a caller, or `BREVIA_STATUS_TOKEN` | `200 {"db_status": "OK"}` or `503 {"db_status": "KO"}`, as in Brevia 0.15 |

The two `/health` endpoints are for the probes of containers and load balancers: use
`/health/live` to restart a process that hangs and `/health/ready` to send it
requests only when it can serve them. `/health/live` only answers; `/health/ready`
checks the database at each call, through
[`Brevia.check`](../reference/application.md#brevia.Brevia.check), and does not return
the reason of a failure: it is in the log. `/status` keeps the monitoring of Brevia
0.15 working, with the same rule: it needs the token of a caller as a Bearer token, or
`BREVIA_STATUS_TOKEN`, when set, as `?token=` or as a Bearer token, so that a
monitoring service needs no caller token. With authentication disabled it is open.

## Compared with Brevia 0.15

| | Brevia 0.15 | Brevia 1.0 |
|---|---|---|
| Building the app | the project creates the FastAPI app and calls `add_routers(app)` and `app_events(app)` | `create_app(brevia)` returns the app, the project adds its endpoints |
| Tokens | checked only if `TOKENS_SECRET` was set when the routers were imported | checked for every request; no secret means no start |
| Errors | `{"detail": ...}`, different shapes, some errors with status 200 | `{code, message, details, request_id}`, stable codes |
| Documentation | hidden with `BLOCK_OPENAPI_URLS` | hidden with `create_app(..., docs=False)` |
| Monitoring | `GET /status` with `STATUS_TOKEN` | the same `/status`, plus `/health/live` and `/health/ready` |
| Direct runs | `/chat`: the answer with `chat_history_id`, the identifier for `/evaluate`, and optional `token_data`; `/completion`: the text with `usage` | `run_id`, `status` and `output`; usage in the log and in the database, not in the answer |
| Jobs | run in background tasks of the API process, lost at each restart | `POST /runs` answers `202`; durable jobs in worker processes |
| Output files | download without a token, by path | `GET /runs/{run_id}/files/{name}`, only for the caller that may see the job |
| Feedback | `POST /evaluate`: good or bad and a comment, overwritten on the row of a chat exchange | `POST /runs/{run_id}/feedback` on any recorded run: corrections or a rating, only added, with caller, end user and an external reference |
| Configuration | `GET`/`POST /config` and `/config/reset` on the settings of the installation, for any valid token | per activity, `/configurations` and `/prompts`, changes only by administrators, with version check and prompt history |

## Request examples

[HTTP examples](http-examples.md) covers every endpoint, including analysis activities invoked through `POST /runs`, with curl requests, response shapes and error cases.
