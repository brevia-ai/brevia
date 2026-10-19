# HTTP examples

Use an application built by `create_app`, with its activities registered and a worker
for jobs. Set `BASE=http://localhost:8000` and `TOKEN` to a token issued by
`brevia token create`. JSON shown below illustrates the relevant fields, not exact
model content. All errors except health-probe bodies have `code`, `message`,
`details` and `request_id`. See [HTTP API](http-api.md) for the complete contracts.

## Discover activities

```sh
curl "$BASE/activities" -H "Authorization: Bearer $TOKEN"
curl "$BASE/activities/document.summarize" -H "Authorization: Bearer $TOKEN"
```

The list has names, versions and supported modes; the detail includes input and
output schemas and overridable fields. Missing activity: `404 not_found`.

## Run summarize or extract

```sh
curl "$BASE/runs" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"activity":"document.summarize","mode":"direct","input":{"text":"A short document.","language":"English"}}'
```

A successful direct run returns `200 {"run_id":"…","status":"succeeded",
"output":{"summary":"…"}}`. For a registered extraction activity use its name
and `{"file":{"name":"invoice.pdf","url":"https://files.example.org/invoice.pdf"}}`
as input; its output follows the project's schema. The URL host must be allowed by
`BREVIA_FILES_ALLOWED_HOSTS`. Size and SHA-256 may be supplied for verification.

The [analysis guide](analysis.md) shows how to register both activities. There are
no dedicated `/summarize` or `/extract` endpoints. Invalid input or model output:
`422`; provider failure: `502`; unavailable storage: `503`.

## Submit and follow a job

```sh
curl "$BASE/runs" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: summary-1' \
  -d '{"activity":"document.summarize","mode":"job","input":{"file":{"name":"report.pdf","url":"https://files.example.org/report.pdf"}}}'
# Set RUN to the run_id in the 202 response.
curl "$BASE/runs/$RUN" -H "Authorization: Bearer $TOKEN"
curl "$BASE/runs/$RUN/result" -H "Authorization: Bearer $TOKEN"
curl "$BASE/runs?activity=document.summarize&idempotency_key=summary-1" -H "Authorization: Bearer $TOKEN"
```

Submission returns `202` with a job state and `Location`. The list returns
`{"jobs":[…],"next_cursor":null}`; pass a non-null cursor as `cursor` to continue.
Status is `queued`, `running`, `succeeded`, `failed` or `cancelled`. Result returns
`200` with the output when successful, `409 not_ready` while pending, or `409` with
the run's error code after failure. Same key with different input: `409`.

## Cancel or retry

```sh
curl -X POST "$BASE/runs/$RUN/cancel" -H "Authorization: Bearer $TOKEN"
curl -X POST "$BASE/runs/$RUN/retry" -H "Authorization: Bearer $TOKEN" -H 'Idempotency-Key: retry-1'
```

Cancellation returns the current job state; cancellation of a running job may take
time. Retry creates a new job for a failed or cancelled run, retaining the original
owner. An active job cannot be retried (`409 busy`); a succeeded job gives
`422 unsupported`. Neither operation accepts a new input or an end user.

## Download an output

```sh
curl "$BASE/runs/$RUN/files/notes.md" -H "Authorization: Bearer $TOKEN" -o notes.md
```

Returns the bytes saved under that name by the job, including by `save_file`.
Missing file, expired output or inaccessible job: `404`. A summary alone does not
create an output file.

## Add feedback

```sh
curl "$BASE/runs/$RUN/feedback" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: review-1' \
  -d '{"kind":"rating","rating":"good","source":"reviewer","end_user":"user-42"}'
```

Returns `201` with the recorded feedback and its id. Corrections use
`kind=correction` and `items` containing `target`, `original`, `corrected` instead of
`rating`. Different feedback with the same key: `409`; invalid fields: `422`.
There is no feedback read endpoint yet. Recorded direct runs also accept feedback.

## Read or change configuration

```sh
curl "$BASE/configurations" -H "Authorization: Bearer $TOKEN"
curl "$BASE/configurations/document.summarize" -H "Authorization: Bearer $TOKEN"
curl -X PATCH "$BASE/configurations/document.summarize" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"values":{"language":"English"},"expected_version":0}'
curl -X POST "$BASE/configurations/document.summarize/reset" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"fields":["language"],"expected_version":1}'
```

Reads return defaults, effective values, customization, schema and version. Changes
return the new state. The activity must declare `language` customizable
(`customizable=["language"]` in `register_activity`): the `document.summarize` of the
project template does not, and answers `422` to this request until it does. Under
`per-caller`, writes require an administrator (`403` otherwise); non-customizable
fields give `422`, stale versions `412`. Reset with `{}` resets all fields.

## Read or change prompts

```sh
curl "$BASE/prompts" -H "Authorization: Bearer $TOKEN"
curl "$BASE/prompts/document.summarize/summarize" -H "Authorization: Bearer $TOKEN"
curl "$BASE/prompts/document.summarize/summarize/revisions" -H "Authorization: Bearer $TOKEN"
curl -X PUT "$BASE/prompts/document.summarize/summarize" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"text":"Summarise faithfully in {language}.","expected_version":0}'
curl -X POST "$BASE/prompts/document.summarize/summarize/reset" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"expected_version":1}'
```

Read and write responses contain file text, effective text, variables and version;
revisions are newest first. To restore a customization, PUT its historical text as
a new version. A historical reset has null text: use reset again. Wrong variables:
`422`; stale version: `412`; non-admin write: `403`; undeclared prompt: `404`.

## Health and status

```sh
curl "$BASE/health/live"
curl "$BASE/health/ready"
curl "$BASE/status" -H "Authorization: Bearer $TOKEN"
curl -I "$BASE/status" -H "Authorization: Bearer $TOKEN"
```

Live returns `200 {"status":"ok"}` without checking the database; ready returns
`200 {"status":"ready"}` or `503 {"status":"unavailable"}`. Neither needs a token.
Status accepts a caller token or the configured status token and returns
`{"db_status":"OK"}` or `{"db_status":"KO"}` with `503`; HEAD has no body.
Missing or invalid authentication on protected endpoints gives `401`; another
caller's job gives `404` under `per-caller`.
