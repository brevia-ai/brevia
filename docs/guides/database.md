# Database

Read this page to connect Brevia to PostgreSQL, size its connections, migrate its
schema and set up a development database.

Brevia needs PostgreSQL. It records runs, model calls and their contents there, and
keeps the customisations of configuration and prompts with the prompt history, and the
records of jobs. Brevia owns one schema,
`brevia` by default, and the durable state of [jobs](jobs.md) lives in a second one,
`dbos` by default; it never writes outside them.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `BREVIA_DATABASE_URL` | required | Connection URL, `postgresql://user:password@host:5432/database`. The psycopg driver is used whether or not the URL names it (`postgresql+psycopg://`); other drivers and databases are refused |
| `BREVIA_DATABASE_SCHEMA` | `brevia` | Schema of the Brevia tables: lowercase letters, digits and underscores |
| `BREVIA_DATABASE_POOL_SIZE` | `5` | Connections each process keeps open |
| `BREVIA_DATABASE_MAX_OVERFLOW` | `5` | Further connections opened under load and closed afterwards |
| `BREVIA_DATABASE_POOL_TIMEOUT` | `30` | Seconds to wait for a free connection before failing |
| `BREVIA_DATABASE_STATEMENT_TIMEOUT` | `30` | Seconds after which the server cancels a statement |
| `BREVIA_JOBS_SCHEMA` | `dbos` | Schema of the durable state of jobs, kept by the job engine (DBOS); different from the Brevia schema |

The URL is a secret: it is never written to snapshots or logs, it is hidden in the
representation of the settings, and invalid values are reported without it. Errors of
the database driver are reported as [`Unavailable`](errors.md) with the types of their
causes only, because their messages may contain host names or users.

## Connections

Each `Brevia` instance opens its own pool in [`start`](../reference/application.md#brevia.Brevia.start)
and closes it in `stop`. A run borrows a connection for each short write and returns
it at once: no connection is held while an activity works or a model answers, so a
slow model does not exhaust the pool.

Each started `Brevia` instance may open up to `POOL_SIZE + MAX_OVERFLOW` connections;
a process usually has one instance, but two instances in the same process open two
pools. Size the pool so that the total over all instances of all processes stays below
the `max_connections` of the server.
When activities support jobs, each process also opens the connections of the job
engine: up to 5 for an application that submits and reads jobs, and more for a worker,
which also runs the engine (6 more for an idle worker in the laboratory test).

## Schema and migrations

Migrations are an explicit step of a release, run before starting the processes:

```sh
brevia db upgrade    # create the schemas if missing and apply the migrations
brevia db current    # print the revision of the database and the expected one
```

Both commands read `BREVIA_DATABASE_URL`, `BREVIA_DATABASE_SCHEMA` and
`BREVIA_JOBS_SCHEMA` from the environment or `.env`. `brevia db upgrade` also creates or
migrates the schema of jobs; processes never migrate it. `brevia db current` checks the
Brevia schema and exits with status 1 when it is not at the expected revision.
`brevia db cleanup` deletes expired data (see [Cleanup](workers.md#cleanup)); it also
reads the project file, for the retention.

`start` does not migrate: it checks that the schema is at the revision of the
installed version of Brevia and otherwise raises `Unavailable`, with the current and
expected revisions in the details. A database migrated by a newer version is refused
too.

The migrations create every table, index and the Alembic version table in the
configured schema, and queries name it explicitly: Brevia does not depend on
`search_path` and does not use `public`. The role of the URL needs the right to create
the schema, or the schema must exist and belong to it; `public`, `information_schema`
and `pg_*` are refused as Brevia schemas. Several installations can share
one database with different schemas.

## Development database

The repository has a `compose.yaml` with PostgreSQL 18 and pgvector, the same image as
the laboratory, on port 5435:

```sh
docker compose up -d --wait
cp .env.example .env          # BREVIA_DATABASE_URL points to this database
uv run brevia db upgrade
```

Until the first release the initial migration is edited in place rather than followed
by new migrations. After pulling a change to it, recreate the development schema:

```sh
docker compose exec postgres psql -U brevia -c 'DROP SCHEMA brevia CASCADE; DROP SCHEMA dbos CASCADE'
uv run brevia db upgrade
```

Use the value of `BREVIA_JOBS_SCHEMA` instead of `dbos` if it was changed.

## Tables

| Table | Content |
|---|---|
| `runs` | One row per run: input, snapshot, status, result or error, usage |
| `model_calls` | One row per model call of a run: model, effective options, tokens, cost, duration |
| `trace_contents` | Contents of model calls of activities with `capture="full"`, with their expiry |
| `configurations` | Customisation of the configuration of each activity, with its version |
| `prompts` | Customised text of each prompt, with its version |
| `prompt_revisions` | History of the changes of each prompt; rows are only added |
| `feedback` | [Feedback](runs.md#feedback) on runs: kind (`correction` or `rating`), source, corrections (`items`), rating, comment, external reference, caller and end user, idempotency key, time; rows are only added |

Which of these rows expire, and when, is in [Data retention](runs.md#data-retention).
Input, snapshot, result and usage are columns of the same row of `runs`: reading a job
reads them all, also while waiting for its result.

## Limits

- The extension and tables for vectors (pgvector) are not created yet; they come with
  the knowledge module.
- Records of direct runs are written but cannot be read through Brevia yet (see
  [Recorded runs](runs.md#limits)).
