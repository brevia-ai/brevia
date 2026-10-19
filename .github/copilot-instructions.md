# Instructions for GitHub Copilot

Brevia 1.0 is a general-purpose Python library for building AI applications. Its design covers layered configuration with snapshots, prompts, model adapters with validated structured output, registered activities, durable jobs (DBOS), files, access control, usage tracking and a FastAPI layer; consumer projects install it and register their own activities. This describes the target: the library is in early development.

The complete rules for agents are in `AGENTS.md`, and the development rules are in `CONTRIBUTING.md`. Do not assume that linked documents are read automatically: the essentials follow.

- **Boundaries.** The stable public API is what `brevia` and its documented modules (`brevia.analysis`, `brevia.tools`, `brevia.api`, `brevia.testing`) export; Pydantic AI and DBOS must not leak into it. Client rules and business workflows belong to consumer projects, not to the library.
- **Status.** `docs/IMPLEMENTATION.md` states what is implemented. Describe as available only what it records as implemented in a completed stage.
- **Code.** Python 3.12+, Ruff formatting (88 characters), mypy strict, English identifiers, docstrings for public behaviour, errors and effects. Explicit dependencies, no global mutable state, no input or output at import time, no silent fallbacks. Standard `logging` with one logger per module; never log secrets, documents or full prompts.
- **Tests.** pytest with the markers `unit` (default), `integration` (real database) and `ai` (real model provider, costs). A simulated model does not prove the quality of a real one.
- **Documentation.** Public features come with Google-style docstrings and a page or section in `docs/` (Zensical site, built in strict mode); planned features are never documented as available.
- **Changes.** One purpose per pull request; incompatible changes to the API, configuration, snapshots, stored data or job resumption must be declared.

## Code review

Follow the procedure in `.github/skills/code-review/SKILL.md`: report only concrete defects introduced or worsened by the change, with file, line, triggering condition and consequence, and check whether the tests can detect the regressions the change risks. Write review comments in English.
