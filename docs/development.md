# Contributing

Brevia is developed in stages, each starting from an approved plan and ending with a
reviewed pull request. The rules for people and for coding agents are in the
repository:

- [`CONTRIBUTING.md`](https://github.com/brevia-ai/brevia/blob/1.x/CONTRIBUTING.md):
  workflow, style, typing, structure, reliability, logging and tests.
- [`AGENTS.md`](https://github.com/brevia-ai/brevia/blob/1.x/AGENTS.md): rules for
  coding agents, including authorisations and reporting.
- [Architecture](architecture.md): how the package is organised, how a run and a job
  flow through the modules, who writes each record, and the invariants to keep.
- [Implementation status](IMPLEMENTATION.md): what is implemented, how it relates to
  the specification, deviations and known limits.
- [Implementation log](implementation-log.md): each change and the evidence collected
  for it.

## Documentation

Every public feature is documented when it is added: docstrings for the API reference,
and a page or section of these guides with its behaviour, errors and limits. Examples
must match the real API. The site is built in strict mode, so broken links and missing
references fail the build:

```sh
uv run --group docs zensical build --strict
uv run --group docs zensical serve   # local preview
```
