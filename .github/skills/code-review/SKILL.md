---
name: code-review
description: Review Brevia pull requests and code changes for concrete defects, functional and AI regressions, test adequacy, public API and compatibility, durable execution and the boundary with consumer projects. Use when reviewing code or documentation changes in this repository.
---

# Brevia code review

## Scope

The review is read-only. Do not modify files, install dependencies, start services, call model providers or run tests unless explicitly asked. Do not report credentials, tokens or client data.

## Preparation

1. Read the diff and identify the behaviours it changes, directly and indirectly, and the requirements they must preserve.
2. Read [AGENTS.md](../../../AGENTS.md) for boundaries and [CONTRIBUTING.md](../../../CONTRIBUTING.md) for style, structure, logging and tests. Size thresholds are review signals, not errors: do not ask for refactoring outside the purpose of the change or for meaningless fragmentation.
3. Read [docs/IMPLEMENTATION.md](../../../docs/IMPLEMENTATION.md) (and, for the history of a part, [docs/implementation-log.md](../../../docs/implementation-log.md)) for the stage, the sections of the specification involved and the declared deviations. Consult the specification ([docs/spec/PROGETTO-BREVIA-1.0.md](../../../docs/spec/PROGETTO-BREVIA-1.0.md)) for the sections the change implements.
4. Follow callers, imports and resources affected by the diff in the code. Use the versions in `uv.lock`: documentation of another version does not prove the behaviour of the installed one.

## Targeted checks

Apply only the checks relevant to the change.

- **Public API and compatibility.** Is what `brevia` exports intended, typed and documented? Does an internal type (Pydantic AI, DBOS, SQLAlchemy) leak into it? Are incompatible changes to the API, configuration, snapshots, stored data or the resumption of existing jobs declared, with their effect?
- **Library boundary.** Client rules, document formats and business workflows belong to consumer projects. Flag domain logic entering the library and general capabilities designed around a single client.
- **Configuration and prompts.** Is the precedence of the configuration levels respected? Are overrides limited to those declared? Do runs use their own snapshot rather than the current configuration? Are prompt variables declared and validated?
- **Models and structured output.** Is output validated, and are retries bounded? Are run limits (requests, tool calls, tokens, time) enforced, including failed attempts? Is usage recorded, with an unknown cost reported as unknown rather than zero? Are provider capabilities declared rather than inferred from model names?
- **Durable execution.** Follow job identifiers, idempotency keys, checkpoints, retries, cancellation and external effects. Look for effects repeated on resume, results overwritten or published twice, partial results presented as complete, and workflows that cannot resume after a release.
- **Persistence and migrations.** Are migrations reversible or explicitly irreversible, consistent with the models and safe on existing data? Do concurrent updates have control? Is the library schema kept separate from the DBOS schema?
- **Access and files.** Can a caller reach runs or files of another caller? Are file fingerprints verified, and is access only by identifier? Are tokens and secrets kept out of logs, errors and traces?
- **Reliability.** Swallowed exceptions, silent fallbacks, missing timeouts or cancellation, blocking work on the event loop, resources not released.
- **Logging and traces.** One logger per module, uniform levels, identifiers propagated, no sensitive content in ordinary logs, no logging configuration at import time.

## Tests and AI regressions

- Link each changed behaviour to its tests and read the assertions: can they detect the concrete regression the change risks? Do they cover errors, limits and significant edge cases? Report concrete gaps; do not ask for tests that duplicate the implementation.
- Changes to prompts, schemas, models, tools, retrieval or configuration can change AI behaviour even when the code is unchanged. Evaluate correctness, adherence to sources, structured output, tool choice, usage and limits for the function involved.
- Flag removed cases, weakened thresholds and expectations changed only to make a check pass. An intentional change must be motivated by the requirements.
- For variable output, criteria and thresholds on versioned datasets matter, not textual identity. Comparisons are interpretable only when models, prompts, configurations and conditions are recorded.
- Distinguish simulated models, deterministic tests, evaluations with real models and human review. A simulated model does not prove the quality of a real one. State the relevant checks that are missing, without running them.

## Result

Report, concisely, only concrete defects introduced or worsened by the diff. For each one give the priority, the file and line, the condition that triggers it and its consequence, with evidence from the code or from the current requirements. Prefer localised comments; avoid duplicates, style remarks covered by the formatter, optional refactoring and unproven hypotheses.

Do not report as new a limit that is already declared in `docs/IMPLEMENTATION.md` and unchanged; do report it if the change worsens it or presents it as solved.

If no concrete defect emerges, say so without claiming that tests passed, that runtime behaviour was verified or that the change is free of problems.
