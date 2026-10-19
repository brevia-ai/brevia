# Getting started

This page builds, from an empty folder, a project with one activity that summarises a
text with a model, and runs it from Python. It takes about ten minutes with a database
and a provider key at hand. The [Concepts](concepts.md) page explains the terms used
here; the guides linked at the end cover each part in depth.

## What you need

- Python 3.12 or later and [uv](https://docs.astral.sh/uv/) (pip works too).
- A PostgreSQL database where you may create schemas. Brevia is tested with
  PostgreSQL 18; see [Database](guides/database.md).
- An API key of a supported provider, here `OPENAI_API_KEY`. Anthropic and local
  Ollama models work the same way; see [Models and limits](guides/models.md).

## Or start from the project template

The steps below build a project by hand, to show each part. To start a real application,
generate it from the Copier template of the repository:

```sh
uvx copier copy --vcs-ref v1.0.0b1 gh:brevia-ai/brevia my-project
```

The project has one activity like the one of this page, organised in modules, with its
HTTP API, a worker, a caller and tests with a fake model: see
[Project template](guides/project-template.md) for its parts and commands.
`uvx copier update`, run in the project, takes the changes of a newer template.

## 1. Create the project and install Brevia

Install Brevia from PyPI, pinned to a release:

```sh
uv init --bare summaries
cd summaries
uv add "brevia==1.0.0b1"
# or, from a local checkout:  uv add --editable ../brevia
# or, with pip:               pip install "brevia==1.0.0b1"
```

The package is imported as `brevia` and installs the `brevia` command. 1.0 is a
pre-release, so the version must be given: without it, pip and uv install Brevia 0.15.
The releases are listed in the [changelog](https://github.com/brevia-ai/brevia/blob/1.x/CHANGELOG.md).

## 2. The files of the project

At the end of this page the project contains:

```text
summaries/
├── pyproject.toml        # created by uv: the dependencies of the project
├── .env                  # settings and credentials, never committed
├── brevia.toml           # project file: models, limits, activity defaults
├── prompts/
│   └── summary.md        # prompt template of the activity
├── summary.py            # the activity: schemas and function
└── main.py               # creates Brevia, registers the activity, runs it
```

## 3. Settings and database

Create `.env` with the database URL and the provider key:

```sh
BREVIA_DATABASE_URL=postgresql://brevia:brevia@localhost:5432/brevia
OPENAI_API_KEY=sk-...
```

Brevia reads its own settings, the `BREVIA_` variables, from the environment and from
the `.env` file of the working directory. Provider keys are read by the providers from
the process environment only, which is why the example runs with
`uv run --env-file .env` below. The other settings, all optional, are listed in
[Database](guides/database.md#settings) and [Logging](guides/logging.md).

Create the Brevia schemas in the database:

```sh
uv run brevia db upgrade
```

```text
Schema brevia at revision 0001
Jobs schema dbos migrated
```

Run it again at every upgrade of Brevia: an application checks the schema when it
starts and refuses to work on an old one, but never migrates it by itself.

## 4. The project file

`brevia.toml` declares the models the project may use, the limits of each run and the
defaults of each activity:

```toml
[limits]
max_requests = 10
max_seconds = 120

[models."openai:gpt-6-luna"]
# Capabilities and prices are declared here: see the models guide.

[activities."document.summarize"]
model = "openai:gpt-6-luna"
language = "it"
```

A model must be declared before an activity can use it. Without declared prices, the
cost of a run is reported as unknown; capabilities, prices and the other limits are in
[Models and limits](guides/models.md).

## 5. The prompt

`prompts/summary.md` is the template of the instructions. A placeholder is `{name}`
with a lowercase name, and every placeholder must receive a value:

```text
Summarise the document in {language}.
Keep the main facts, the numbers and the uncertainties.
Do not add information that is not in the document.
```

## 6. The activity

`summary.py` holds the three schemas of the activity and its function:

```python
from pydantic import BaseModel, Field

from brevia import RunContext


class SummaryRequest(BaseModel):
    """Input of one run."""

    text: str = Field(min_length=1)


class SummaryConfig(BaseModel):
    """Settings of the activity, composed for each run."""

    model: str
    max_output_tokens: int = Field(default=1200, gt=0)
    language: str = "it"


class SummaryResult(BaseModel):
    """Output of the activity, validated before it is returned."""

    summary: str


async def summarize(
    request: SummaryRequest, ctx: RunContext[SummaryConfig]
) -> SummaryResult:
    result: SummaryResult = await ctx.model().generate(
        instructions=ctx.prompt("summary").render(language=ctx.config.language),
        user_text=request.text,
        output_type=SummaryResult,
        max_output_tokens=ctx.config.max_output_tokens,
    )
    return result
```

The function receives the validated input and a
[`RunContext`](reference/runs.md#brevia.RunContext): `ctx.config` is the configuration of
this run, `ctx.prompt()` a declared prompt and `ctx.model()` a client of the configured
model, whose `generate()` returns an output already validated against `SummaryResult`.

## 7. Registration and run

`main.py` creates Brevia, registers the activity and runs it once:

```python
import asyncio

from brevia import Brevia, BreviaSettings, configure_logging
from summary import SummaryConfig, SummaryRequest, SummaryResult, summarize

settings = BreviaSettings()
configure_logging(settings.log_level, settings.log_format)
brevia = Brevia.from_settings(settings)
brevia.register_activity(
    name="document.summarize",
    version="1",
    function=summarize,
    input_type=SummaryRequest,
    output_type=SummaryResult,
    config_type=SummaryConfig,
    prompts={"summary": "prompts/summary.md"},
    overridable=["language"],
)


async def main() -> None:
    async with brevia:  # connects to the database and checks its schema
        result = await brevia.run(
            "document.summarize",
            SummaryRequest(text="The document to summarise..."),
            overrides={"language": "en"},
        )
    print(result.model_dump_json(indent=2))


asyncio.run(main())
```

- Registration reads the prompt files and validates the defaults of `brevia.toml`, so
  a configuration error stops the program here, before any run.
- `async with brevia` opens the database connections and closes them at the end; a run
  needs a started Brevia.
- The project file sets `language = "it"`; this request asks for English with an
  override. `overridable=["language"]` is what allows it: an override of any other
  field is refused. How defaults, customisations and overrides combine is in
  [Configuration](guides/configuration.md).

Run it:

```sh
uv run --env-file .env python main.py
```

The log goes to the standard error and the result to the standard output; times,
tokens and identifiers vary:

```text
2026-10-16 10:00:00,120 INFO brevia.db.store Database store started: schema brevia, revision 0001
2026-10-16 10:00:00,135 INFO brevia.runs.execution Run started: document.summarize version 1, overrides ['language'] [run 3f6c...]
2026-10-16 10:00:03,402 INFO brevia.models.client Model call openai:gpt-6-luna: 1 requests, 128 input and 64 output tokens, 3.250 s [run 3f6c...]
2026-10-16 10:00:03,410 INFO brevia.runs.execution Run succeeded: document.summarize in 3.275 s, 1 model requests, cost unknown [run 3f6c...]
{
  "summary": "..."
}
```

The run, its snapshot of the values in use, its outcome and its model calls are now in
the database: see [Recorded runs](guides/runs.md).

## When something goes wrong

| What you see | Cause | What to do |
|---|---|---|
| `brevia: settings are not valid` (command), `pydantic.ValidationError` (Python) naming `database_url` | `BREVIA_DATABASE_URL` is missing or is not a PostgreSQL URL | Set it in `.env`, in the working directory |
| `Unavailable`: `Database schema is not at the expected revision: run brevia db upgrade` | The schema was never created, or Brevia was upgraded | Run `uv run brevia db upgrade` |
| `brevia: database operation failed (...)` or `Unavailable` at start | The database cannot be reached | Check host, port, user and password |
| `Unavailable` at registration: `Default model of activity 'document.summarize' is not declared in the project` | The model is missing from `[models]` in `brevia.toml` | Declare it |
| `Unavailable` during the run: `Model 'openai:gpt-6-luna' cannot be used: check the provider credentials...` | The provider key is not in the process environment | Run with `uv run --env-file .env`, or export the key |
| `OverrideNotAllowed` | The request overrides a field not listed in `overridable` | Add the field to `overridable`, or drop the override |
| `InvalidInput` | The input does not match `SummaryRequest`, for example an empty text | Fix the input; the error details name the fields |

A run that fails after it started is recorded as failed with its error. All error
types and their details are in [Errors](guides/errors.md).

## Next steps

- [Concepts](concepts.md): activities, runs, jobs and snapshots, and how they fit.
- [Configuration](guides/configuration.md): how defaults, customisations and overrides
  compose.
- [Prompts](guides/prompts.md): template rules and customisation with history.
- [Models and limits](guides/models.md): capabilities, prices, retries, usage and
  costs.
- [Recorded runs](guides/runs.md): what is stored for each run.
- [Testing](guides/testing.md): fake models, to test activities without a provider.
- [Jobs](guides/jobs.md): durable runs in a worker, with idempotency, cancellation and
  retry.
