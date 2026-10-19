# Brevia

Brevia is a Python library for building AI applications in internal projects. A project
installs Brevia, registers its own *activities* (typed functions that may call models)
and runs them from Python code or through an HTTP API.

Brevia takes care of what every AI feature needs and what is costly to add afterwards:
configuration with defaults and controlled overrides, prompts with declared variables,
model calls with validated structured output and bounded retries, run limits, usage and
cost tracking, and consistent errors and logs. The domain logic stays in the project.

!!! warning "Beta"
    Brevia 1.0 is in beta, for controlled use in internal projects: the features
    below work and are tested, but the API and the database schema may still change
    before 1.0. The [implementation status](IMPLEMENTATION.md) has the details and
    the known limits.

## In the beta

- Activities with typed input, output and configuration, run directly from Python.
- Configuration composed from project defaults, database customisations and the
  overrides each activity allows.
- Prompt templates with declared variables, customisable in the database with history.
- Optional recording of the contents of model calls, with a retention period.
- Structured generation with OpenAI, Anthropic and Ollama models, with capabilities and
  prices declared in the project.
- Per-run limits on model requests, tool calls, tokens and time.
- A catalogue of errors shared by the Python API and the HTTP API.
- Logging helpers for text and JSON output.
- Runs recorded in PostgreSQL with their snapshot, outcome and model calls, in a
  dedicated schema managed with `brevia db upgrade`.
- Durable jobs that survive restarts, with idempotency, cancellation, retry, lists by
  caller and a worker command.
- Input files downloaded from allowed hosts or copied, and output files saved with the
  run, with SHA-256 fingerprints.
- Document readers for PDF, DOCX and text files, which keep pages and headings.
- Pipelines over long documents (`map_reduce`, `refine`) and the ready `summarize` and
  `extract` activities.
- Tools that the model may call during a generation, among them reading and saving
  the files of the run.
- Access control with JWT tokens compatible with Brevia 0.15 and a per-caller access
  policy.
- Structured feedback on runs: corrections or a rating.
- A project template for new applications, with a container image that runs their
  worker and API, together or apart.
- An HTTP API built by `create_app`, with health endpoints, activities, runs and jobs,
  configuration and prompts, feedback, and OpenAPI documentation with Swagger UI and
  ReDoc.

## Not in the beta

- Knowledge bases (RAG) and conversations (chat).
- Streaming of answers to the caller: a run returns its whole output at the end.
- Upload of files and storage adapters: inputs are files of allowed hosts or local
  paths.
- Model adapters registered by the project, beyond OpenAI, Anthropic and Ollama.
- Reading the model calls of a run from Python or HTTP; evaluation datasets.

## What may still change

- **Models verified.** Real calls are verified with OpenAI. Anthropic and Ollama are
  tested with simulated providers only: not verified with real models.
- **Database.** Until 1.0 the initial migration may still change instead of adding a
  new one: a new beta may need a new database (or its `brevia` and `dbos` schemas
  dropped and created again). The release notes say when.
- **API.** Any part may change before 1.0, declared in the
  [changelog](https://github.com/brevia-ai/brevia/blob/1.x/CHANGELOG.md). The
  youngest parts are the most likely to: `brevia.analysis`, `brevia.tools` and the
  prompts of the package.

## How to read this documentation

- **Quick start**: [Getting started](getting-started.md) builds a first activity, then
  [Concepts](concepts.md) explains the parts it uses.
- **Guides**: one task each (configuration, models, jobs, files, analysis, HTTP
  API...), with the behaviour, the errors and the limits of the feature.
- **API reference**: every public class and function, generated from the code, with
  the default of each parameter.
