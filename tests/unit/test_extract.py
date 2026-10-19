"""The extract function with a schema of the project, the prompts of the package and a
fake model."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from conftest import Recorder, simulated
from memory_store import MemoryStore
from pydantic import BaseModel

from brevia import (
    Brevia,
    Document,
    FileSource,
    FileStore,
    InvalidInput,
    NotFound,
    RunContext,
)
from brevia.analysis import (
    EXTRACT_PROMPTS,
    SUMMARIZE_PROMPTS,
    ExtractConfig,
    ExtractRequest,
    extract,
    extract_document,
    summarize_document,
)
from brevia.config.project import load_project

pytestmark = pytest.mark.unit

MODEL = "openai:test-model"
PROJECT = f"""
[limits]
max_requests = 20

[models."{MODEL}"]

[activities."invoice.extract"]
model = "{MODEL}"
max_input_chars = 60

[activities."invoice.custom"]
model = "{MODEL}"
currency = "USD"

[activities."invoice.undeclared"]
model = "{MODEL}"

[activities."invoice.paid"]
model = "{MODEL}"
max_input_chars = 60

[activities."invoice.digest"]
model = "{MODEL}"
"""


PAID_RULES = "Extract only the invoices marked as paid."


class Invoice(BaseModel):
    numbers: list[str]
    total: int


def check_total(invoice: Invoice) -> list[str]:
    return [] if invoice.total >= 0 else ["the total cannot be negative"]


async def extract_invoice(
    request: ExtractRequest, ctx: RunContext[ExtractConfig]
) -> Invoice:
    return await extract(ctx, request, Invoice, validator=check_total)


class InvoiceConfig(ExtractConfig):
    currency: str = "EUR"


async def extract_custom(
    request: ExtractRequest, ctx: RunContext[InvoiceConfig]
) -> Invoice:
    # Type-checked by mypy: the context of a subclassed configuration is accepted.
    assert ctx.config.currency == "USD"
    return await extract(ctx, request, Invoice)


async def extract_undeclared(
    request: ExtractRequest, ctx: RunContext[ExtractConfig]
) -> Invoice:
    return await extract_document(ctx, Document.from_text("N1"), Invoice)


class Digest(BaseModel):
    summary: str
    invoices: Invoice


async def digest(request: ExtractRequest, ctx: RunContext[ExtractConfig]) -> Digest:
    # Both ready functions in one activity, on a long document: each uses its own
    # prompts, declared together.
    document = Document.from_text(request.text or "")
    summary = await summarize_document(
        ctx, document, language="English", max_input_chars=60
    )
    found = await extract_document(ctx, document, Invoice, max_input_chars=60)
    return Digest(summary=summary.summary, invoices=found)


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[Brevia]:
    (tmp_path / "brevia.toml").write_text(PROJECT, encoding="utf-8")
    (tmp_path / "paid.md").write_text(PAID_RULES, encoding="utf-8")
    brevia = Brevia(
        load_project(tmp_path / "brevia.toml"),
        project_dir=tmp_path,
        store=MemoryStore(),
        files=FileStore(tmp_path / "files"),
    )
    brevia.register_activity(
        name="invoice.extract",
        version="1",
        function=extract_invoice,
        input_type=ExtractRequest,
        output_type=Invoice,
        config_type=ExtractConfig,
        prompts=EXTRACT_PROMPTS,
        modes=("direct", "job"),
    )
    brevia.register_activity(
        name="invoice.custom",
        version="1",
        function=extract_custom,
        input_type=ExtractRequest,
        output_type=Invoice,
        config_type=InvoiceConfig,
        prompts=EXTRACT_PROMPTS,
    )
    brevia.register_activity(
        name="invoice.undeclared",
        version="1",
        function=extract_undeclared,
        input_type=ExtractRequest,
        output_type=Invoice,
        config_type=ExtractConfig,
    )
    brevia.register_activity(
        name="invoice.paid",
        version="1",
        function=extract_invoice,
        input_type=ExtractRequest,
        output_type=Invoice,
        config_type=ExtractConfig,
        prompts={**EXTRACT_PROMPTS, "extract_rules": "paid.md"},
    )
    brevia.register_activity(
        name="invoice.digest",
        version="1",
        function=digest,
        input_type=ExtractRequest,
        output_type=Digest,
        config_type=ExtractConfig,
        prompts={**SUMMARIZE_PROMPTS, **EXTRACT_PROMPTS},
    )
    async with brevia:
        yield brevia


def invoices(instructions: str, text: str) -> dict[str, Any]:
    """Numbers are the words starting with "N", the total their count."""
    found: list[str] = []
    if "so far, as JSON, is:" in instructions:
        found = json.loads(
            instructions.split("so far, as JSON, is:\n\n", 1)[1].split("\n\n")[0]
        )["numbers"]
    found += [word for word in text.split() if word.startswith("N")]
    return {"numbers": found, "total": len(found)}


async def test_a_short_document_takes_one_call(app: Brevia) -> None:
    recorder = Recorder(invoices)
    with simulated(recorder.model()):
        result = await app.run(
            "invoice.extract", ExtractRequest(text="Invoices N1 and N2 paid.")
        )

    assert result == Invoice(numbers=["N1", "N2"], total=2)
    [(instructions, text)] = recorder.calls
    assert instructions.startswith("Extract from the document")
    assert text == "Invoices N1 and N2 paid."


async def test_a_long_document_is_refined_piece_by_piece(app: Brevia) -> None:
    text = "\n\n".join(f"Page {n} with invoice N{n} " + "x" * 30 for n in range(3))
    recorder = Recorder(invoices)
    with simulated(recorder.model()):
        result = await app.run("invoice.extract", ExtractRequest(text=text))

    assert result == Invoice(numbers=["N0", "N1", "N2"], total=3)
    assert len(recorder.calls) == 3
    assert all(len(user) <= 60 for _, user in recorder.calls)
    assert recorder.calls[0][0].startswith("Extract from the document")
    assert recorder.calls[0][0].startswith("Extract from the document")
    assert recorder.calls[2][0].startswith("You are extracting data")
    assert '"numbers": [\n    "N0",\n    "N1"\n  ]' in recorder.calls[2][0]


async def test_the_validator_of_the_project_checks_the_data(app: Brevia) -> None:
    answers = iter([{"numbers": [], "total": -1}, {"numbers": [], "total": 0}])
    recorder = Recorder(lambda *_: next(answers))
    with simulated(recorder.model()):
        result = await app.run("invoice.extract", ExtractRequest(text="Nothing."))

    assert result == Invoice(numbers=[], total=0)
    assert len(recorder.retries) == 1
    assert "the total cannot be negative" in recorder.retries[0]


async def test_a_file_is_read_and_extracted(app: Brevia, tmp_path: Path) -> None:
    path = tmp_path / "invoices.txt"
    path.write_text("N7 paid.", encoding="utf-8")
    recorder = Recorder(invoices)
    with simulated(recorder.model()):
        result = await app.run(
            "invoice.extract",
            ExtractRequest(file=FileSource(name="invoices.txt", path=path)),
        )

    assert result == Invoice(numbers=["N7"], total=1)


def test_the_prompts_are_files_of_the_package() -> None:
    assert set(EXTRACT_PROMPTS) == {"extract", "extract_refine"}
    assert all(path.is_file() for path in EXTRACT_PROMPTS.values())
    assert "{previous}" in EXTRACT_PROMPTS["extract_refine"].read_text(encoding="utf-8")


async def test_a_subclassed_configuration_is_accepted(app: Brevia) -> None:
    recorder = Recorder(invoices)
    with simulated(recorder.model()):
        result = await app.run("invoice.custom", ExtractRequest(text="N5 due."))

    assert result == Invoice(numbers=["N5"], total=1)


async def test_the_validator_checks_every_refine_step(app: Brevia) -> None:
    text = "\n\n".join(f"Page {n} with invoice N{n} " + "x" * 30 for n in range(2))
    wrong = iter([True])

    def respond(instructions: str, user: str) -> dict[str, Any]:
        answer = invoices(instructions, user)
        if "so far, as JSON, is:" in instructions and next(wrong, False):
            answer["total"] = -1
        return answer

    recorder = Recorder(respond)
    with simulated(recorder.model()):
        result = await app.run("invoice.extract", ExtractRequest(text=text))

    assert result == Invoice(numbers=["N0", "N1"], total=2)
    assert len(recorder.retries) == 1
    assert "the total cannot be negative" in recorder.retries[0]


async def test_both_sources_are_refused(app: Brevia) -> None:
    with pytest.raises(InvalidInput):
        await app.run("invoice.extract", {})
    with pytest.raises(InvalidInput):
        await app.run(
            "invoice.extract",
            {"text": "a", "file": {"name": "a.txt", "path": "/a.txt"}},
        )


async def test_extract_document_needs_the_prompts_declared(app: Brevia) -> None:
    with simulated(Recorder(invoices).model()), pytest.raises(NotFound):
        await app.run("invoice.undeclared", ExtractRequest(text="unused"))


async def test_the_rules_of_the_project_reach_every_piece(app: Brevia) -> None:
    text = "\n\n".join(f"Page {n} with invoice N{n} " + "x" * 30 for n in range(3))
    recorder = Recorder(invoices)
    with simulated(recorder.model()):
        await app.run("invoice.paid", ExtractRequest(text=text))

    assert len(recorder.calls) == 3
    assert all(
        instructions.endswith(f"\n\n{PAID_RULES}") for instructions, _ in recorder.calls
    )


async def test_summary_and_extraction_in_one_activity(app: Brevia) -> None:
    text = "\n\n".join(f"Page {n} with invoice N{n} " + "x" * 30 for n in range(3))

    def respond(instructions: str, user: str) -> dict[str, Any]:
        if "Summarise" in instructions or "summaries" in instructions:
            return {"summary": "Pages."}
        return invoices(instructions, user)

    recorder = Recorder(respond)
    with simulated(recorder.model()):
        result = await app.run("invoice.digest", ExtractRequest(text=text))

    assert result == Digest(
        summary="Pages.", invoices=Invoice(numbers=["N0", "N1", "N2"], total=3)
    )
