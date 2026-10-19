"""Logging helpers for applications that use Brevia.

The library only emits records through ``logging.getLogger(__name__)`` loggers and never
configures logging by itself. An application may call :func:`configure_logging` once at
start-up, or configure the standard ``logging`` module in its own way.

Records about runs carry ``run_id`` and ``activity`` attributes, which the JSON format
includes. Records never contain credentials, tokens, documents or full prompts and
responses.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Literal

CONTEXT_FIELDS = ("run_id", "activity", "request_id")
"""Record attributes added by Brevia to correlate events."""


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for production logs."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name in CONTEXT_FIELDS:
            value = getattr(record, name, None)
            if value is not None:
                entry[name] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Readable lines for development, with the run or request identifier when
    present."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        tags = [
            f"[{label} {value}]"
            for label, value in (
                ("run", getattr(record, "run_id", None)),
                ("request", getattr(record, "request_id", None)),
            )
            if value
        ]
        if not tags:
            return text
        # On the first line, before any stack frames that follow the message.
        first, newline, rest = text.partition("\n")
        return f"{first} {' '.join(tags)}{newline}{rest}"


def configure_logging(
    level: str = "INFO", log_format: Literal["text", "json"] = "text"
) -> None:
    """Configure the root logger to write to the standard error.

    Replaces the handlers of the root logger, so it is meant to be called once by
    the application, not by libraries.

    Args:
        level: ``DEBUG``, ``INFO``, ``WARNING`` or ``ERROR``.
        log_format: ``text`` for development, ``json`` for production.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if log_format == "json" else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
