"""Defaults of Brevia, in one place.

Every functional default of the library is here; the classes and functions of Brevia
refer to these values instead of repeating them. A project replaces them in its project
file (``brevia.toml``): the ``[limits]`` table for the limits of a run, ``[traces]`` for
the retention of traces, and the table of each activity for its configuration,
including the model use. ``0`` (:data:`NO_LIMIT`) turns a run limit or the retention
off. A default that is ``None`` applies when the value is left out of the file. The
project template writes the defaults out, so a new project shows the values it uses.

Settings of the installation (database, files, logs) are not here: they are
environment variables, read by :class:`brevia.BreviaSettings`.
"""

from __future__ import annotations

from typing import Final

NO_LIMIT: Final = 0
"""Value of a run limit or of the trace retention that turns it off."""

MODEL_MAX_TOKENS: Final[int | None] = None
"""Most tokens that each model request may generate, reasoning tokens included;
``None`` sends no limit, so the response may reach the maximum of the model."""

GENERATION_MAX_ATTEMPTS: Final = 3
"""Attempts of a generation to obtain an output valid for its schema and validator."""

RUN_MAX_REQUESTS: Final = 20
"""Model requests of a run, retries included: a guard against a model that loops."""

RUN_MAX_TOOL_CALLS: Final = NO_LIMIT
"""Tool calls of a run."""

RUN_MAX_TOTAL_TOKENS: Final = NO_LIMIT
"""Input and output tokens of a run."""

RUN_MAX_SECONDS: Final = 900.0
"""Duration of a run, in seconds: a guard against a provider that does not answer."""

RUN_PROVIDER_RETRIES: Final = 2
"""Retries of a request after a temporary provider error."""

SUMMARIZE_LANGUAGE: Final[str | None] = None
"""Language of the summaries of :func:`brevia.analysis.summarize`; ``None`` keeps the
language of the document."""

SUMMARIZE_STRATEGY: Final = "auto"
"""Strategy of :func:`brevia.analysis.summarize` for a document longer than one call."""

SUMMARIZE_MAX_INPUT_CHARS: Final = 120_000
"""Longest text that :func:`brevia.analysis.summarize` sends in one call."""

EXTRACT_MAX_INPUT_CHARS: Final = 120_000
"""Longest text that :func:`brevia.analysis.extract` sends in one call."""

TRACE_RETENTION_DAYS: Final = NO_LIMIT
"""Days the contents of model calls, and the recorded steps of ended jobs, are kept;
``0`` keeps them without a time limit."""
