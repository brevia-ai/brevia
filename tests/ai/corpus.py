"""Synthetic corpus for the ready analysis activities, with separate measures.

Each case is a short or long text in Italian with what a correct answer contains: the
facts a summary must keep, or the values an extraction must find (``None`` where the
document does not have them). Kinds: ``normal``, ``long`` (longer than one call, so
divided into pieces), ``incomplete``, ``contradictory`` (a value corrected later in
the text), ``negative`` (nothing to find) and ``impossible`` (refused before any call).

:func:`run_corpus` runs every case on a started :class:`~brevia.Brevia` with the
activities of :func:`register` and returns one :class:`Measure` per case: whether the
output is valid for the schema (or the expected refusal came), whether it is faithful
(no number or value that the document does not support), its completeness, the
model requests, the cost and the time. The measures are computed in code, without a
model as judge, so they are coarse: a fact is found by its words or digits.

Used by ``tests/ai/test_corpus.py`` with a real model, and by a unit test with a fake
model, which checks the harness, not the quality.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from brevia import Brevia, BreviaError, RunContext
from brevia.analysis import (
    EXTRACT_PROMPTS,
    SUMMARIZE_PROMPTS,
    ExtractConfig,
    ExtractRequest,
    SummarizeConfig,
    SummarizeRequest,
    Summary,
    extract,
    summarize,
)
from brevia.db.runs import RunOutcome

Kind = Literal[
    "normal", "long", "incomplete", "contradictory", "negative", "impossible"
]

MAX_INPUT_CHARS = 2000
"""Longest text of one call in the corpus: the long cases go over it."""

SUMMARIZE = "corpus.summarize"
EXTRACT = "corpus.extract"


class Minutes(BaseModel):
    """Data of the minutes of a meeting; a field the text does not have stays empty."""

    meeting_date: str | None = Field(
        default=None, description="Date of the meeting, as YYYY-MM-DD."
    )
    attendees: int | None = Field(default=None, description="Members present.")
    approved_budget_eur: Decimal | None = Field(
        default=None, description="Budget approved, in euro, as a number."
    )
    next_meeting_date: str | None = Field(
        default=None, description="Date of the next meeting, as YYYY-MM-DD."
    )


async def extract_minutes(
    request: ExtractRequest, ctx: RunContext[ExtractConfig]
) -> Minutes:
    return await extract(ctx, request, Minutes)


def register(brevia: Brevia) -> None:
    """Register the two activities of the corpus: ``summarize`` and an extraction."""
    brevia.register_activity(
        name=SUMMARIZE,
        version="1",
        function=summarize,
        input_type=SummarizeRequest,
        output_type=Summary,
        config_type=SummarizeConfig,
        prompts=SUMMARIZE_PROMPTS,
    )
    brevia.register_activity(
        name=EXTRACT,
        version="1",
        function=extract_minutes,
        input_type=ExtractRequest,
        output_type=Minutes,
        config_type=ExtractConfig,
        prompts=EXTRACT_PROMPTS,
    )


def project(model: str, model_table: str) -> str:
    """Project file of the corpus for ``model``, declared by ``model_table``."""
    return f"""
[limits]
max_requests = 20
max_seconds = 300

[models."{model}"]
{model_table}

[activities."{SUMMARIZE}"]
model = "{model}"
language = "Italian"
max_input_chars = {MAX_INPUT_CHARS}

[activities."{EXTRACT}"]
model = "{model}"
max_input_chars = {MAX_INPUT_CHARS}
"""


# ---------- cases ----------


@dataclass(frozen=True)
class Case:
    """A document and what a correct answer has.

    ``facts`` are the words or numbers a summary must keep; ``expected`` the values of
    an extraction, ``None`` where the document has none; ``error`` the code of an
    expected refusal.
    """

    id: str
    task: Literal["summarize", "extract"]
    kind: Kind
    text: str
    facts: tuple[str, ...] = ()
    expected: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


FILLER = (
    "L'assemblea ha discusso il regolamento condominiale, la pulizia delle scale "
    "e il calendario della manutenzione ordinaria, senza prendere "
    "decisioni su questi punti. Gli interventi sono stati brevi e il dibattito si è "
    "svolto in modo ordinato. "
)


def _long(first: str, last: str) -> str:
    """A text with ``first`` at the start and ``last`` at the end, longer than one
    call."""
    middle = "\n\n".join(
        f"Punto {n} dell'ordine del giorno. {FILLER * 3}" for n in range(1, 6)
    )
    return f"{first}\n\n{middle}\n\n{last}"


MINUTES = (
    "Verbale dell'assemblea condominiale del 12 marzo 2026. Sono presenti 7 "
    "condòmini. L'assemblea approva il preventivo dei lavori straordinari con una "
    "spesa complessiva di 1.250.000 euro. La prossima assemblea è fissata per il "
    "9 aprile 2026."
)

OLIVES = (
    "Nel terzo trimestre la cooperativa ha lavorato 1.240 tonnellate di olive, il 18% "
    "in più dell'anno precedente. La resa in olio è scesa al 14,2% per l'estate "
    "secca, quindi la produzione totale di olio è cresciuta solo del 6%."
)

CASES: tuple[Case, ...] = (
    Case(
        id="summary-normal",
        task="summarize",
        kind="normal",
        text=OLIVES,
        facts=("1240", "18", "14,2"),
    ),
    Case(
        id="summary-long",
        task="summarize",
        kind="long",
        text=_long(
            "Verbale del 3 febbraio 2026. L'assemblea approva la sostituzione "
            "dell'ascensore per 320.000 euro.",
            "In chiusura l'amministratore comunica che i lavori sul tetto "
            "inizieranno entro giugno.",
        ),
        facts=("320000", "ascensore", "tetto"),
    ),
    Case(
        id="summary-contradictory",
        task="summarize",
        kind="contradictory",
        text=(
            "L'assemblea approva una spesa di 45.000 euro per la facciata. In fondo "
            "alla seduta l'amministratore rettifica l'importo: la spesa approvata è "
            "di 40.000 euro, per un errore di calcolo nel preventivo."
        ),
        facts=("40000",),
    ),
    Case(
        id="summary-negative",
        task="summarize",
        kind="negative",
        text="Documento di prova. Non contiene informazioni.",
    ),
    Case(
        id="summary-impossible",
        task="summarize",
        kind="impossible",
        text="   ",
        error="invalid_input",
    ),
    Case(
        id="extract-normal",
        task="extract",
        kind="normal",
        text=MINUTES,
        expected={
            "meeting_date": "2026-03-12",
            "attendees": 7,
            "approved_budget_eur": Decimal("1250000"),
            "next_meeting_date": "2026-04-09",
        },
    ),
    Case(
        id="extract-long",
        task="extract",
        kind="long",
        text=_long(
            "Verbale dell'assemblea condominiale del 5 maggio 2026. Sono presenti "
            "9 condòmini.",
            "Al termine l'assemblea approva il preventivo con una spesa di 980.000 "
            "euro e fissa la prossima assemblea al 2 giugno 2026.",
        ),
        expected={
            "meeting_date": "2026-05-05",
            "attendees": 9,
            "approved_budget_eur": Decimal("980000"),
            "next_meeting_date": "2026-06-02",
        },
    ),
    Case(
        id="extract-incomplete",
        task="extract",
        kind="incomplete",
        text=(
            "Verbale dell'assemblea condominiale del 20 gennaio 2026. Sono presenti "
            "5 condòmini. Il preventivo non viene discusso e la data della prossima "
            "assemblea sarà comunicata."
        ),
        expected={
            "meeting_date": "2026-01-20",
            "attendees": 5,
            "approved_budget_eur": None,
            "next_meeting_date": None,
        },
    ),
    Case(
        id="extract-contradictory",
        task="extract",
        kind="contradictory",
        text=(
            "Verbale dell'assemblea del 14 ottobre 2026. Sono presenti 6 condòmini. "
            "L'assemblea approva il preventivo con una spesa di 1.200.000 euro. A fine "
            "seduta l'amministratore rettifica: la spesa approvata è di 1.180.000 euro."
        ),
        expected={
            "meeting_date": "2026-10-14",
            "attendees": 6,
            "approved_budget_eur": Decimal("1180000"),
            "next_meeting_date": None,
        },
    ),
    Case(
        id="extract-negative",
        task="extract",
        kind="negative",
        text=(
            "Ricetta della bruschetta: tostare il pane, strofinare l'aglio, "
            "aggiungere olio e sale."
        ),
        expected={
            "meeting_date": None,
            "attendees": None,
            "approved_budget_eur": None,
            "next_meeting_date": None,
        },
    ),
)


# ---------- measures ----------


@dataclass(frozen=True)
class Measure:
    """The measures of one case, kept apart: a valid output may be unfaithful."""

    case: str
    task: str
    kind: str
    status: str
    error: str | None
    valid: bool
    faithful: bool
    unsupported: list[str]
    completeness: float | None
    requests: int
    cost_usd: str | None
    seconds: float
    output: dict[str, Any] | None


def _number(text: str) -> str:
    """``text`` as a number without thousands separators and with a decimal point:
    ``1.240`` and ``1,240`` are ``1240``, ``14,2`` is ``14.2``."""
    return re.sub(r"[.,](?=\d{3}\b)", "", text).replace(",", ".")


def _digits(text: str) -> set[str]:
    """The numbers in ``text``, normalised by :func:`_number`."""
    return {_number(n) for n in re.findall(r"\d+(?:[.,]\d+)*", text)}


def _has(text: str, fact: str) -> bool:
    if fact.replace(",", "").isdigit():
        return _number(fact) in _digits(text)
    return fact.lower() in text.lower()


def summary_measures(case: Case, summary: str) -> tuple[bool, list[str], float | None]:
    """Faithful when every number of the summary is in the document; completeness
    as the share of the facts kept."""
    unsupported = sorted(_digits(summary) - _digits(case.text))
    if not case.facts:
        return not unsupported, unsupported, None
    kept = sum(_has(summary, fact) for fact in case.facts)
    return not unsupported, unsupported, kept / len(case.facts)


def extraction_measures(
    case: Case, output: dict[str, Any]
) -> tuple[bool, list[str], float | None]:
    """Faithful when no value differs from the expected one, a value found where the
    document has none included; completeness as the share of expected values found."""
    unsupported = sorted(
        name
        for name, value in output.items()
        if value is not None and value != case.expected.get(name)
    )
    present = [name for name, value in case.expected.items() if value is not None]
    if not present:
        return not unsupported, unsupported, None
    found = sum(output.get(name) == case.expected[name] for name in present)
    return not unsupported, unsupported, found / len(present)


def _measure(
    case: Case,
    outcome: RunOutcome | None,
    output: BaseModel | None,
    error: BreviaError | None,
    seconds: float,
) -> Measure:
    code = None if error is None else error.code
    usage = outcome.usage if outcome is not None else {}
    data = None if output is None else output.model_dump()
    unsupported: list[str]
    if data is None:
        faithful, unsupported, completeness = case.error is not None, [], None
    elif case.task == "summarize":
        faithful, unsupported, completeness = summary_measures(case, data["summary"])
    else:
        faithful, unsupported, completeness = extraction_measures(case, data)
    return Measure(
        case=case.id,
        task=case.task,
        kind=case.kind,
        status="succeeded" if error is None else "failed",
        error=code,
        valid=code == case.error,
        faithful=faithful,
        unsupported=unsupported,
        completeness=completeness,
        requests=int(usage.get("requests", 0)),
        cost_usd=usage.get("cost_usd"),
        seconds=round(seconds, 2),
        output=data,
    )


async def run_corpus(
    brevia: Brevia, outcomes: dict[uuid.UUID, RunOutcome]
) -> list[Measure]:
    """Run every case, one after the other, and measure it.

    ``outcomes`` are the outcomes recorded by the store of ``brevia``, read for the
    usage of each run.
    """
    measures = []
    for case in CASES:
        run_id = uuid.uuid4()
        name = SUMMARIZE if case.task == "summarize" else EXTRACT
        output: BaseModel | None = None
        error: BreviaError | None = None
        started = time.monotonic()
        try:
            output = await brevia.run(name, {"text": case.text}, run_id=str(run_id))
        except BreviaError as exc:
            error = exc
        seconds = time.monotonic() - started
        measures.append(_measure(case, outcomes.get(run_id), output, error, seconds))
    return measures


def report(measures: list[Measure]) -> str:
    """A table of the measures, one line per case, then the totals."""
    lines = [
        f"{'case':24} {'valid':5} {'faith':5} {'compl':5} {'req':>3} "
        f"{'cost $':>9} {'s':>6}  notes"
    ]
    for m in measures:
        completeness = "-" if m.completeness is None else f"{m.completeness:.2f}"
        notes = m.error or ""
        if m.unsupported:
            notes += f" unsupported: {', '.join(m.unsupported)}"
        lines.append(
            f"{m.case:24} {m.valid!s:5} {m.faithful!s:5} {completeness:5} "
            f"{m.requests:>3} {m.cost_usd or '-':>9} {m.seconds:>6}  {notes.strip()}"
        )
    costs = [Decimal(m.cost_usd) for m in measures if m.cost_usd is not None]
    lines.append(
        f"valid {sum(m.valid for m in measures)}/{len(measures)}, faithful "
        f"{sum(m.faithful for m in measures)}/{len(measures)}, requests "
        f"{sum(m.requests for m in measures)}, cost {sum(costs, Decimal(0))} USD, "
        f"{sum(m.seconds for m in measures):.1f} s"
    )
    return "\n".join(lines)


def report_json(measures: list[Measure]) -> str:
    """The measures as JSON, to keep and compare between runs."""
    return json.dumps([asdict(m) for m in measures], default=str, indent=2)
