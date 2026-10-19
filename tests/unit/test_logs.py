"""Logging: run identifiers in records, no prompts or user data, JSON format."""

from __future__ import annotations

import json
import logging
import sys

import pytest
from conftest import answers, simulated

from brevia import Brevia
from brevia.runs.logs import JsonFormatter, TextFormatter

pytestmark = pytest.mark.unit


async def test_run_records_carry_the_run_id_and_no_document_text(
    brevia: Brevia,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG), simulated(answers({"summary": "ok"})):
        await brevia.run("document.summarize", {"text": "CONFIDENTIAL CONTENT"})
    records = [r for r in caplog.records if r.name.startswith("brevia")]
    model_calls = [r for r in records if r.msg.startswith("Model call")]
    assert records
    assert model_calls
    # Every record of the run, model calls included, carries the same run identifier.
    assert len({getattr(r, "run_id", None) for r in records}) == 1
    assert getattr(records[0], "run_id", None) is not None
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "CONFIDENTIAL" not in text
    assert "Summarise the document" not in text


def test_json_formatter_includes_context_fields() -> None:
    record = logging.LogRecord(
        "brevia.x", logging.INFO, __file__, 1, "done", None, None
    )
    record.run_id = "abc"
    entry = json.loads(JsonFormatter().format(record))
    assert entry["run_id"] == "abc"
    assert entry["message"] == "done"
    assert entry["level"] == "INFO"


def test_importing_brevia_installs_no_handler() -> None:
    assert logging.getLogger("brevia").handlers == []


def test_text_format_puts_the_run_id_on_the_first_line() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "brevia.x", logging.ERROR, __file__, 1, "failed", None, sys.exc_info()
        )
    record.run_id = "abc"
    first_line = TextFormatter().format(record).splitlines()[0]
    assert first_line.endswith("failed [run abc]")


def test_text_format_shows_the_request_id_of_http_errors() -> None:
    record = logging.LogRecord(
        "brevia.api", logging.ERROR, __file__, 1, "failed", None, None
    )
    record.request_id = "r1"
    assert TextFormatter().format(record).endswith("failed [request r1]")
    assert json.loads(JsonFormatter().format(record))["request_id"] == "r1"
