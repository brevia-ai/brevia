"""The synthetic corpus of ``corpus.py`` with a real OpenAI model.

Runs only on request (``uv run --env-file .env pytest -m ai tests/ai/test_corpus.py
-s``) and needs ``OPENAI_API_KEY``; no database (runs are kept in memory). It calls
the provider about twenty times and incurs a small cost. It prints a table of the
measures and, with ``BREVIA_CORPUS_REPORT`` set to a path, writes them there as JSON.

It fails when an output is not valid for its schema (or an expected refusal does not
come) or is not faithful: a number of a summary or a value of an extraction that the
document does not support. Completeness, requests, cost and time are reported, not
checked: they are measures to compare between models and versions.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from memory_store import MemoryStore

from ai.corpus import project, register, report, report_json, run_corpus
from brevia import Brevia
from brevia.config.project import load_project

pytestmark = [
    pytest.mark.ai,
    pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY is not set"
    ),
]

MODEL = "openai:gpt-6-luna"
# Official OpenAI prices verified on 2026-10-10 (USD per million tokens).
MODEL_TABLE = """reasoning_levels = ["low", "medium", "high"]
temperature = false
prices = { input = 0.10, cached_input = 0.01, output = 0.50 }"""


async def test_the_corpus_with_a_real_model(tmp_path: Path) -> None:
    (tmp_path / "brevia.toml").write_text(project(MODEL, MODEL_TABLE), encoding="utf-8")
    store = MemoryStore()
    brevia = Brevia(
        load_project(tmp_path / "brevia.toml"), project_dir=tmp_path, store=store
    )
    register(brevia)
    async with brevia:
        measures = await run_corpus(brevia, store.outcomes)

    print(f"\n{MODEL}\n{report(measures)}")
    path = os.environ.get("BREVIA_CORPUS_REPORT")
    if path:
        await asyncio.to_thread(
            Path(path).write_text, report_json(measures), encoding="utf-8"
        )
    assert [m.case for m in measures if not m.valid] == []
    assert [m.case for m in measures if not m.faithful] == []
