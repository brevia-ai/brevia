# Running in production

Read this page before installing an application built on Brevia on a server: what it
needs, how to start and update it, what to back up and where to look when something
fails. Each section points to the guide with the details. The examples use an
application generated from the [project template](project-template.md), whose package
is `myproject`.

## What an installation needs

- **PostgreSQL**, tested with version 18. Brevia uses two schemas of one database: its
  own (`brevia`) and the one of jobs (`dbos`). See [Database](database.md).
- **Brevia pinned to a release**, `brevia @ git+https://github.com/nikazzio/brevia-next@v1.0.0b1`
  in the dependencies of the application, with the lockfile committed.
- **A folder on persistent storage** for the files of runs, if activities save
  outputs (`BREVIA_FILES_ROOT`). See [Files](files.md).
- **The environment** of each process, API and workers alike:

| Variable | Value |
|---|---|
| `BREVIA_DATABASE_URL` | URL of the database, a secret |
| `BREVIA_PROJECT_FILE` | Path of the project file, if it is not `brevia.toml` in the working folder |
| `BREVIA_TOKENS_SECRET`, `BREVIA_TOKENS_USERS` | Secret of the caller tokens and the callers accepted; `BREVIA_AUTH_DISABLED` never in production. See [Callers](access.md#settings) |
| `BREVIA_FILES_ROOT` | The persistent folder above |
| `BREVIA_LOG_FORMAT` | `json`, for a log collector. See [Logging](logging.md) |
| `OPENAI_API_KEY` (or the key of another provider) | Credentials of the provider, exported in the environment of the process |
| `BREVIA_STATUS_TOKEN` | Optional: token of `GET /status` for a monitoring tool |

Every setting and its default are in [Configuration](configuration.md).

## Start

The image of the [project template](project-template.md#in-a-container) is the
recommended way: one image runs every process, chosen by `APP_MODE`, and stops the
worker in order. Two ways to deploy it:

- **One service in mode `all`**, for a small installation: the worker and the API in
  one container, with a volume for `BREVIA_FILES_ROOT`. When either process ends on
  its own the container exits with an error and the platform starts it again.
- **Two services from the same image**, `api` and `worker`, to scale or restart them
  apart. Both need the same files of runs, so `BREVIA_FILES_ROOT` must be on a volume
  that the two services share.

In both:

1. **Migrate the database** once per release, before the processes start: the image
   with `APP_MODE=migrate`, as the pre-deploy command of the platform or a run of its
   own. Processes never migrate; `brevia db current` prints the revision of the
   database and the expected one.
2. **Set `BREVIA_APP_VERSION`** to the release of the image, and **`BREVIA_WORKER_ID`**
   to a fixed name for each worker service, never shared by two running workers: the
   host name of a container changes at every deploy, and a worker starts again after
   a restart only the jobs recorded under its own name. See [Workers](workers.md).
3. **Set the stop timeout of the platform** to `BREVIA_WORKER_SHUTDOWN_SECONDS` (30 by
   default) plus a few seconds. Some platforms stop a container at once by default:
   the running jobs are then interrupted and start again from the beginning.
4. **Point the probes** to `GET /health/live` (restart the container when it does not
   answer) and `GET /health/ready` (send requests only when the database answers).
   `/health/ready` does not say whether a worker is running jobs. See
   [HTTP API](http-api.md#health).

Without the image, start the same processes with a process manager:

1. `brevia db upgrade`, as in step 1.
2. **The API**: `uvicorn myproject.api:app --host 0.0.0.0 --port 8000`, without
   `--reload`, with the probes of step 4.
3. **The workers**, at least one if any activity runs as a job:
   `brevia worker myproject.application:create`, with a `BREVIA_WORKER_ID` of its own
   for each. A worker also runs the daily cleanup of expired data.

## Update

1. Read the release notes in the changelog. During the beta, a release may change the
   initial migration: the notes then say that the `brevia` and `dbos` schemas must be
   created again, which loses runs, jobs and customisations (back them up first, or
   export the customisations you need).
2. Pin the new tag in the application, update its lockfile and deploy the new code.
3. Run `brevia db upgrade`.
4. Stop all the workers of the previous release, then start those of the new one.
   Jobs interrupted by the update fail as retryable and can be retried. See
   [Releases](workers.md#releases).

## Backup and restore

The data of an installation is in three places:

| Where | What | Lost without a backup |
|---|---|---|
| Schema `brevia` | Runs, model calls and their contents, customisations of configuration and prompts with their history, feedback | Everything recorded, and the customisations, which exist only there |
| Schema `dbos` (`BREVIA_JOBS_SCHEMA`) | Queued and running jobs, the recorded steps of jobs | Jobs not finished yet |
| `BREVIA_FILES_ROOT` | Outputs saved by runs | The files the callers have not read yet |

A backup copies the two schemas (named by `BREVIA_DATABASE_SCHEMA` and
`BREVIA_JOBS_SCHEMA`, `brevia` and `dbos` by default) and the folder at about the same
time, for example:

```sh
pg_dump --format=custom --schema=brevia --schema=dbos "$DATABASE_URL" > brevia.dump
tar czf brevia-files.tgz -C "$BREVIA_FILES_ROOT" .
```

To restore, stop the API and the workers, restore the schemas
(`pg_restore --clean --if-exists --dbname="$DATABASE_URL" brevia.dump`) and the
folder, check the revision with `brevia db current`, then start the processes. Jobs
that were running when the backup was taken start again from the beginning, as after
any stop of a worker. The provider is never involved: credentials stay in the
environment, not in the backup.

## When something fails

- **The answer of the API** has `code`, `message` and `request_id`; the code says what
  failed and whether repeating can help. See [Errors](errors.md).
- **The logs** have a line for every run and model call with its `run_id`, without
  documents or prompts. A server error (`5xx`) is logged with the `request_id` of the
  answer. See [Logging](logging.md).
- **The database** has every run in `brevia.runs` (status, error, usage, snapshot) and
  its model calls in `brevia.model_calls`, with the identifier of each provider
  request for the support of the provider. See [Recorded runs](runs.md).
- Frequent causes: `unavailable` with the database down or not migrated
  (`brevia db current`); `provider_error` with missing credentials or a provider
  that is down; `limit_exceeded` and `run_timeout` with limits too low for the
  document; `output_invalid` when the model does not produce valid data within the
  attempts.

## Reporting a problem

Open an issue on the repository of Brevia with the version (`brevia.__version__`), the
error code and message, the `run_id` or `request_id`, the lines of the log around it
and the steps that lead to it. Never attach `.env` files, credentials, documents or
other data of clients: describe the document instead (format, size, pages).
