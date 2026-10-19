"""The published example uses the actual public API with no provider or database."""

import importlib.util
from pathlib import Path

import pytest
from memory_store import MemoryStore

from brevia import Brevia
from brevia.config.project import load_project

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


async def test_published_analysis_examples() -> None:
    spec = importlib.util.spec_from_file_location(
        "analysis_example", ROOT / "examples" / "analysis_pipeline.py"
    )
    assert spec is not None
    assert spec.loader is not None
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    store = MemoryStore()
    app = Brevia(
        load_project(ROOT / "examples" / "analysis.toml"), store=store, project_dir=ROOT
    )
    example.register(app)
    async with app:
        results = await example.run_examples(app)
    assert len(results) == 7
    for name, result in results.items():
        expected = (
            {"number": "INV-1"}
            if "extract" in name
            else {"summary": "Synthetic summary."}
        )
        assert result.model_dump() == expected
    assert len(store.runs) == 7
