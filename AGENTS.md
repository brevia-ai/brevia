# Instructions for coding agents

These rules apply to every agent that works on this repository (Claude Code, Codex, GitHub Copilot and others). Tool-specific files only import or summarise them; if a rule seems to differ between files, this file prevails and the discrepancy must be reported.

## The project

Brevia 1.0 is a general-purpose Python library for building AI applications in internal projects. Its design covers layered configuration with snapshots, prompts, model adapters with validated structured output, registered activities, durable jobs, files, access control, usage tracking and a FastAPI layer; a consumer project installs the library, registers its own activities and mounts the routers it needs. This describes the target, not the current state. The requirements of consumer projects guide the order of development, never the design of the library.

The repository is at an early stage. [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md) states what exists, what is in progress and what is planned. Describe as available only what it records as implemented in a completed stage.

## Authoritative sources

Consult them in this order, and read code before describing how something works:

1. **The code, the tests and `uv.lock`** for the current behaviour and dependency versions. Documentation of a different dependency version does not prove the behaviour of the installed one.
2. **[docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)** for progress, deviations from the specification and known limits; **[docs/implementation-log.md](docs/implementation-log.md)** for each change and the evidence collected for it.
3. **The specification**, [docs/spec/PROGETTO-BREVIA-1.0.md](docs/spec/PROGETTO-BREVIA-1.0.md) (written in Italian). It defines components, data, API and verification criteria. Decisions recorded there are not reopened implicitly: propose a change explicitly and explain why; a change agreed with the maintainer updates the specification in the same pull request.
4. **[CONTRIBUTING.md](CONTRIBUTING.md)** for style, typing, structure, logging, tests and the change workflow.

One reference is useful but is not a specification: Brevia 0.15 (`brevia-ai/brevia`), the technical and functional reference of the previous generation, not a design to replicate.

## Architecture and boundaries

- The stable public API is what `brevia` exports and what the documented modules `brevia.analysis`, `brevia.tools`, `brevia.api` and `brevia.testing` list in `__all__`. Everything else is internal. Pydantic AI and DBOS are implementation details and must not leak into the public API.
- The library holds only general capabilities useful to several projects. Client rules, document formats, report contents and business workflows belong to the consumer project. When a requirement comes from a single client, look for the general capability behind it or leave it to the consumer.
- Keep the core, the adapters (models, storage) and the functional modules separate. Introduce an abstraction only when it isolates a concrete variation.
- The HTTP API is a thin layer over the same Python operations; a feature must not exist only behind an endpoint.
- Do not confuse the agents that develop this code with the application agents that the library runs.

## Working method

- Work proceeds in stages listed in `docs/IMPLEMENTATION.md`. Each stage starts with a plan that the maintainer approves before any code is written; agents that offer a planning mode use it.
- One recognisable purpose per change and per pull request. Keep reformatting, dependency updates and functional changes in separate pull requests.
- Each change adds an entry to `docs/implementation-log.md`: what changed and the evidence, stating which checks were run and of which kind. It updates `docs/IMPLEMENTATION.md` when it changes the status of a stage or section, a deviation, a known limit or a planned item, and `CHANGELOG.md` when it affects users of the library.
- Each public feature is documented when it is added: docstrings for the API reference and a page or section of the documentation site (`docs/`) with its behaviour, errors and limits. Examples must match the real API, and the site must build in strict mode.
- Never weaken a test, remove a case or change an expectation only to make a check pass. An intentional change of behaviour must be motivated by the requirements.

## Commands

Run from the repository root:

```sh
uv sync --locked              # development environment from the lockfile
uv run ruff format --check    # formatting
uv run ruff check             # lint
uv run mypy                   # type checking (strict)
uv run pytest                 # unit tests only, by default
uv run --env-file .env pytest -m ai   # real providers, only on request
uv run --group docs zensical build --strict   # documentation site
```

## Authorisations

- Static checks and unit tests may be run at any time during development: they are deterministic and have no external effects.
- The following require an explicit request from the maintainer: integration tests (`pytest -m integration`), tests with real model providers (`pytest -m ai`), any call to a model provider, adding or upgrading dependencies, starting services or containers, database migrations on a real database, and anything that publishes or deletes data.
- Commit, push, open or merge a pull request only when asked. Never force-push unless asked.
- Documenting a command does not authorise running it.

## Reporting

- State which checks were actually run and of which kind: static, unit (simulated), integration with a real database, or with a real model. Checks that were not run are stated as such.
- A passing test does not prove the absence of regressions, and a simulated model does not prove the quality of a real one.
- Distinguish the specification, the implementation and the evidence. Do not present a proposal as implemented.

## Git

- Use the maintainer's Git identity. Do not add `Co-Authored-By` lines or any other reference to an agent in commit messages, pull request descriptions or code.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`), in English.

## Data and secrets

No client data, credentials, tokens or `.env` files in the repository, in tests, in examples or in logs. Test data is synthetic. Credentials for local runs go in the `.env` file at the repository root, created from `.env.example` and ignored by Git; never read the `.env` or the environment of another project.

Personal notes and agent memory (for example `CLAUDE.local.md`) may help with preferences and context, but they are not a source of truth for the project: decisions and progress belong in the versioned documents.

## Language

Code, documentation and commit messages are in English, except the specification, which is in Italian. Conversations with the maintainer are in Italian.
