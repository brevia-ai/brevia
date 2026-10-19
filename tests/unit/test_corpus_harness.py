"""The harness of the synthetic corpus (``tests/ai/corpus.py``) with a fake model: it
runs every case and computes the measures. The quality is measured only with a real
model (``tests/ai/test_corpus.py``)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from memory_store import MemoryStore

from ai.corpus import (
    CASES,
    Case,
    extraction_measures,
    project,
    register,
    report,
    run_corpus,
    summary_measures,
)
from brevia import Brevia
from brevia.config.project import load_project
from brevia.testing import fake_model

pytestmark = pytest.mark.unit

MODEL = "openai:test-model"


async def test_every_case_runs_and_is_measured(tmp_path: Path) -> None:
    (tmp_path / "brevia.toml").write_text(
        project(MODEL, "prices = { input = 1, output = 2 }"), encoding="utf-8"
    )
    store = MemoryStore()
    brevia = Brevia(
        load_project(tmp_path / "brevia.toml"), project_dir=tmp_path, store=store
    )
    register(brevia)
    async with brevia:
        with fake_model():
            measures = await run_corpus(brevia, store.outcomes)

    assert [m.case for m in measures] == [c.id for c in CASES]
    impossible = next(m for m in measures if m.kind == "impossible")
    assert (impossible.valid, impossible.error, impossible.requests) == (
        True,
        "invalid_input",
        0,
    )
    # The long cases are divided into pieces: more than one request.
    assert all(m.requests > 1 for m in measures if m.kind == "long")
    assert all(m.cost_usd is not None for m in measures if m.requests)
    assert len(report(measures).splitlines()) == len(CASES) + 2


def test_a_summary_with_a_number_not_in_the_document_is_not_faithful() -> None:
    case = Case(id="c", task="summarize", kind="normal", text="Lavorate 1.240 t, +18%.")
    assert summary_measures(case, "Lavorate 1,240 t (+18%).") == (True, [], None)
    faithful, unsupported, _ = summary_measures(case, "Lavorate 1.300 t.")
    assert (faithful, unsupported) == (False, ["1300"])


def test_an_extracted_value_not_in_the_document_is_not_faithful() -> None:
    case = Case(
        id="c",
        task="extract",
        kind="incomplete",
        text="",
        expected={"attendees": 5, "approved_budget_eur": None},
    )
    assert extraction_measures(case, {"attendees": 5, "approved_budget_eur": None}) == (
        True,
        [],
        1.0,
    )
    assert extraction_measures(
        case, {"attendees": None, "approved_budget_eur": Decimal(10)}
    ) == (False, ["approved_budget_eur"], 0.0)
