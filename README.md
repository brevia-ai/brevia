# Brevia

Python library for AI applications. Define typed activities; Brevia handles model
calls, validated output, configuration, durable jobs, files and access control.
Your application owns the business logic.

**Beta, for controlled internal use · Python 3.12+ · PostgreSQL · Not published on PyPI**

## What works today

- OpenAI, Anthropic and Ollama models, structured output, retries and run limits.
- Configuration overrides, prompt templates and a snapshot of each run.
- Direct execution or queued jobs with cancellation, retry and worker recovery.
- Input files from allowed HTTPS hosts, output files and automatic cleanup.
- JWT authentication, per-caller access, usage tracking and optional traces.
- An HTTP API for activities, runs and jobs, configuration, prompts and feedback,
  on which the application adds its own endpoints.
- PDF, DOCX and text readers, `map_reduce` and `refine` over long documents, the
  ready `summarize` and `extract` activities and tools the model may call.

An interrupted job restarts its activity from the beginning: external effects must
tolerate repetition. What the beta leaves out, and what may still change before 1.0
(real models verified with OpenAI only; the database schema), is on the
[documentation home](docs/index.md#not-in-the-beta).
See [implementation status](docs/IMPLEMENTATION.md) for guarantees and limits.

## Use it in your application

Start a new application from the [project template](docs/guides/project-template.md):

```sh
uvx copier copy --vcs-ref v1.0.0b1 gh:nikazzio/brevia-next my-project
```

It has one working activity, its HTTP API, a worker, tests with a fake model, a
development database and a container image that runs the worker and the API. To add Brevia to an existing project instead, install it from a
local checkout, using [uv](https://docs.astral.sh/uv/):

```sh
uv add --editable ../brevia-next
```

Or install from Git (repository access required), pinned to the tag of a release:

```sh
uv add "brevia @ git+https://github.com/nikazzio/brevia-next@v1.0.0b1"
```

Follow [Getting started](docs/getting-started.md) for a complete working example:
configure the database and a model, register an activity, then run it from Python.
For background execution, use the [job example](docs/guides/jobs.md#a-complete-example).

## Develop Brevia

From this repository:

```sh
uv sync --locked
cp .env.example .env
```

The example points to the local database in `compose.yaml`. To use it:

```sh
docker compose up -d --wait
uv run brevia db upgrade
```

Set a provider key in `.env` only when calling a real model. Load it into the process
with `uv run --env-file .env python your_script.py`. For development without model
calls, see [fake models](docs/guides/testing.md).

## Configuration

| Where | What belongs there |
|---|---|
| `.env` | Database URL, credentials and installation settings |
| `brevia.toml` | Models, run limits and activity defaults |
| Application code | Activities, input/output schemas and business logic |

[`.env.example`](.env.example) contains the common options; omitted settings use
their defaults. See [all settings](docs/guides/configuration.md),
[worker settings](docs/guides/workers.md#settings) and
[authentication](docs/guides/access.md#authentication) when needed.

## Checks

```sh
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest
```

Unit tests need no services or provider keys. Integration and real-model tests are
separate: see [Contributing](CONTRIBUTING.md#checks).

## Documentation site

Guides and API reference are built from `docs/` and the docstrings:

```sh
uv run --group docs zensical serve            # preview at http://localhost:8000, reloads on changes
uv run --group docs zensical build --strict   # build into site/, failing on broken links
```

Add `--open` to `serve` to open the browser, or `--dev-addr 0.0.0.0:8001` for another
address or port.

| Need | Read |
|---|---|
| Run and operate jobs | [Jobs](docs/guides/jobs.md) · [Workers](docs/guides/workers.md) |
| Handle documents and permissions | [Files](docs/guides/files.md) · [Access](docs/guides/access.md) |
| Use the Python API | [API reference](docs/reference/index.md) |
| Check progress and changes | [Implementation status](docs/IMPLEMENTATION.md) · [Changelog](CHANGELOG.md) |
| Contribute | [Contributing](CONTRIBUTING.md) · [Agent instructions](AGENTS.md) |

## Licence and compatibility

Proprietary; the licence has not been decided. Do not distribute.
Brevia 1.0 is a new design; projects using
[Brevia 0.15](https://github.com/brevia-ai/brevia) require a separate migration.
