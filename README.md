# Brevia

[![CI](https://github.com/brevia-ai/brevia/actions/workflows/ci.yml/badge.svg?branch=1.x)](https://github.com/brevia-ai/brevia/actions/workflows/ci.yml?query=branch%3A1.x)
![Python Versions](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue.svg)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](https://github.com/brevia-ai/brevia/blob/1.x/LICENSE)

Python library for AI applications. Define typed activities; Brevia handles model
calls, validated output, configuration, durable jobs, files and access control.
Your application owns the business logic.

**Beta, for controlled internal use · Python 3.12+ · PostgreSQL · On PyPI as a pre-release: `brevia==1.0.0b1`**

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
[documentation home](https://github.com/brevia-ai/brevia/blob/1.x/docs/index.md#not-in-the-beta).
See [implementation status](https://github.com/brevia-ai/brevia/blob/1.x/docs/IMPLEMENTATION.md) for guarantees and limits.

## Use it in your application

Start a new application from the [project template](https://github.com/brevia-ai/brevia/blob/1.x/docs/guides/project-template.md):

```sh
uvx copier copy --vcs-ref v1.0.0b1 gh:brevia-ai/brevia my-project
```

It has one working activity, its HTTP API, a worker, tests with a fake model, a
development database and a container image that runs the worker and the API. To add
Brevia to an existing project instead, install it from PyPI, pinned to a release, using
[uv](https://docs.astral.sh/uv/):

```sh
uv add "brevia==1.0.0b1"
```

1.0 is a pre-release: `pip install brevia` or `uv add brevia` without a version still
installs Brevia 0.15.

Follow [Getting started](https://github.com/brevia-ai/brevia/blob/1.x/docs/getting-started.md) for a complete working example:
configure the database and a model, register an activity, then run it from Python.
For background execution, use the [job example](https://github.com/brevia-ai/brevia/blob/1.x/docs/guides/jobs.md#a-complete-example).

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
calls, see [fake models](https://github.com/brevia-ai/brevia/blob/1.x/docs/guides/testing.md).

## Configuration

| Where | What belongs there |
|---|---|
| `.env` | Database URL, credentials and installation settings |
| `brevia.toml` | Models, run limits and activity defaults |
| Application code | Activities, input/output schemas and business logic |

[`.env.example`](https://github.com/brevia-ai/brevia/blob/1.x/.env.example) contains the common options; omitted settings use
their defaults. See [all settings](https://github.com/brevia-ai/brevia/blob/1.x/docs/guides/configuration.md),
[worker settings](https://github.com/brevia-ai/brevia/blob/1.x/docs/guides/workers.md#settings) and
[authentication](https://github.com/brevia-ai/brevia/blob/1.x/docs/guides/access.md#authentication) when needed.

## Checks

```sh
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest
```

Unit tests need no services or provider keys. Integration and real-model tests are
separate: see [Contributing](https://github.com/brevia-ai/brevia/blob/1.x/CONTRIBUTING.md#checks).

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
| Run and operate jobs | [Jobs](https://github.com/brevia-ai/brevia/blob/1.x/docs/guides/jobs.md) · [Workers](https://github.com/brevia-ai/brevia/blob/1.x/docs/guides/workers.md) |
| Handle documents and permissions | [Files](https://github.com/brevia-ai/brevia/blob/1.x/docs/guides/files.md) · [Access](https://github.com/brevia-ai/brevia/blob/1.x/docs/guides/access.md) |
| Use the Python API | [API reference](https://github.com/brevia-ai/brevia/blob/1.x/docs/reference/index.md) |
| Check progress and changes | [Implementation status](https://github.com/brevia-ai/brevia/blob/1.x/docs/IMPLEMENTATION.md) · [Changelog](https://github.com/brevia-ai/brevia/blob/1.x/CHANGELOG.md) |
| Contribute | [Contributing](https://github.com/brevia-ai/brevia/blob/1.x/CONTRIBUTING.md) · [Agent instructions](https://github.com/brevia-ai/brevia/blob/1.x/AGENTS.md) |

## Licence and compatibility

[MIT](https://github.com/brevia-ai/brevia/blob/1.x/LICENSE).
Brevia 1.0 is a new design; projects using
[Brevia 0.15](https://github.com/brevia-ai/brevia) require a separate migration.
