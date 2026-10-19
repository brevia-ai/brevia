"""The map_reduce and refine strategies, with a simulated model that records calls."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import Recorder, simulated
from memory_store import MemoryStore
from pydantic import BaseModel

from brevia import (
    Brevia,
    InvalidInput,
    LimitExceeded,
    Piece,
    PromptTemplate,
    RunContext,
)
from brevia.analysis import map_reduce, refine
from brevia.config.project import load_project

pytestmark = pytest.mark.unit

MODEL = "openai:test-model"
PROJECT = f"""
[limits]
max_requests = 20

[models."{MODEL}"]

[activities."test.strategy"]
model = "{MODEL}"

[activities."test.wrong"]
model = "{MODEL}"
"""
PROMPTS = {
    "map": "Summarise this part in {language}.",
    "combine": "Combine these summaries in {language}.",
    "first": "Extract the totals in {language}.",
    "refine": "Update the totals in {language}. So far:\n{previous}",
    "rules": "Only facts about costs.",
    "bad_rules": "Only facts in {language}.",
}


class Config(BaseModel):
    model: str


class Summary(BaseModel):
    summary: str


class Totals(BaseModel):
    count: int
    seen: list[str]


class Request(BaseModel):
    pieces: list[str]
    strategy: str
    max_chars: int | None = None
    partial: bool = False
    rules: str | None = None


Run = Callable[[Request, RunContext[Config]], Any]


async def strategy(request: Request, ctx: RunContext[Config]) -> BaseModel:
    values = {"language": "en"}
    result: BaseModel
    if request.strategy == "map_reduce":
        result = await map_reduce(
            ctx,
            request.pieces,
            output_type=Summary,
            map_prompt=ctx.prompt("map"),
            combine_prompt=ctx.prompt("combine"),
            values=values,
            rules=ctx.prompt(request.rules) if request.rules else None,
            max_chars=request.max_chars,
            partial_type=Totals if request.partial else None,
            validator=lambda output: ["too short"] if len(output.summary) < 3 else [],
        )
    else:
        result = await refine(
            ctx,
            [
                Piece(text=text, start=n, end=n + 1)
                for n, text in enumerate(request.pieces)
            ],
            output_type=Totals,
            first_prompt=ctx.prompt("first"),
            refine_prompt=ctx.prompt("refine"),
            values=values,
            rules=ctx.prompt(request.rules) if request.rules else None,
            validator=lambda output: (
                [] if output.count == len(output.seen) else ["count differs"]
            ),
        )
    return result


@pytest.fixture
async def app(tmp_path: Path) -> Any:
    (tmp_path / "brevia.toml").write_text(PROJECT, encoding="utf-8")
    for name, text in PROMPTS.items():
        (tmp_path / f"{name}.md").write_text(text, encoding="utf-8")
    brevia = Brevia(
        load_project(tmp_path / "brevia.toml"),
        project_dir=tmp_path,
        store=MemoryStore(),
    )
    brevia.register_activity(
        name="test.strategy",
        version="1",
        function=strategy,
        input_type=Request,
        output_type=BaseModel,
        config_type=Config,
        prompts={name: f"{name}.md" for name in PROMPTS},
    )
    async with brevia:
        yield brevia


def summaries(instructions: str, text: str) -> dict[str, Any]:
    return {"summary": f"S[{text}]"}


def as_json(*texts: str) -> str:
    """Partial summaries as the combination receives them: JSON, blank lines between."""
    return "\n\n".join(
        Summary(summary=text).model_dump_json(indent=2) for text in texts
    )


async def test_map_reduce_summarises_each_piece_then_combines(app: Brevia) -> None:
    recorder = Recorder(summaries)
    with simulated(recorder.model()):
        result = await app.run(
            "test.strategy",
            Request(pieces=["one", "two", "three"], strategy="map_reduce"),
        )

    assert recorder.calls == [
        ("Summarise this part in en.", "one"),
        ("Summarise this part in en.", "two"),
        ("Summarise this part in en.", "three"),
        ("Combine these summaries in en.", as_json("S[one]", "S[two]", "S[three]")),
    ]
    assert result == Summary(summary=f"S[{as_json('S[one]', 'S[two]', 'S[three]')}]")


async def test_map_reduce_of_one_piece_needs_no_combination(app: Brevia) -> None:
    recorder = Recorder(summaries)
    with simulated(recorder.model()):
        result = await app.run(
            "test.strategy", Request(pieces=["only"], strategy="map_reduce")
        )

    assert len(recorder.calls) == 1
    assert result == Summary(summary="S[only]")


async def test_map_reduce_combines_in_rounds_within_the_size(app: Brevia) -> None:
    def respond(instructions: str, text: str) -> dict[str, Any]:
        return {"summary": "zzz" if "Combine" in instructions else text}

    recorder = Recorder(respond)
    size = len(as_json("aaa"))  # every partial has the same length
    with simulated(recorder.model()):
        result = await app.run(
            "test.strategy",
            Request(
                pieces=["aaa", "bbb", "ccc", "ddd", "eee"],
                strategy="map_reduce",
                max_chars=2 * size + 2,
            ),
        )

    combines = [
        text for instructions, text in recorder.calls if "Combine" in instructions
    ]
    # Two outputs fit in a group: (a, b), (c, d), (e); then (z, z), (z); then (z, z).
    assert combines == [
        as_json("aaa", "bbb"),
        as_json("ccc", "ddd"),
        as_json("eee"),
        as_json("zzz", "zzz"),
        as_json("zzz"),
        as_json("zzz", "zzz"),
    ]
    assert all(len(text) <= 2 * size + 2 for text in combines)
    assert result == Summary(summary="zzz")


async def test_map_reduce_validates_only_the_combination_with_a_partial_type(
    app: Brevia,
) -> None:
    def respond(instructions: str, text: str) -> dict[str, Any]:
        if "Combine" in instructions:
            return {"summary": "ok!"}
        return {"count": 1, "seen": [text]}

    recorder = Recorder(respond)
    with simulated(recorder.model()):
        result = await app.run(
            "test.strategy",
            Request(pieces=["x"], strategy="map_reduce", partial=True),
        )

    assert [instructions for instructions, _ in recorder.calls] == [
        "Summarise this part in en.",
        "Combine these summaries in en.",
    ]
    assert json.loads(recorder.calls[1][1]) == {"count": 1, "seen": ["x"]}
    assert result == Summary(summary="ok!")


async def test_map_reduce_sends_validator_problems_back(app: Brevia) -> None:
    answers = iter(["no", "fine", "good", "combined"])
    recorder = Recorder(lambda *_: {"summary": next(answers)})
    with simulated(recorder.model()):
        result = await app.run(
            "test.strategy", Request(pieces=["a", "b"], strategy="map_reduce")
        )

    # "no" is too short: the problem goes back to the model, which answers "fine".
    assert len(recorder.retries) == 1
    assert "too short" in recorder.retries[0]
    assert recorder.calls[-1][1] == as_json("fine", "good")
    assert result == Summary(summary="combined")


def totals(instructions: str, text: str) -> dict[str, Any]:
    seen = []
    if "So far:" in instructions:
        seen = json.loads(instructions.split("So far:\n", 1)[1].split("\n\n")[0])[
            "seen"
        ]
    return {"count": len(seen) + 1, "seen": [*seen, text]}


async def test_refine_updates_the_result_with_each_piece(app: Brevia) -> None:
    recorder = Recorder(totals)
    with simulated(recorder.model()):
        result = await app.run(
            "test.strategy", Request(pieces=["p1", "p2", "p3"], strategy="refine")
        )

    assert result == Totals(count=3, seen=["p1", "p2", "p3"])
    assert [text for _, text in recorder.calls] == ["p1", "p2", "p3"]
    assert recorder.calls[0][0] == "Extract the totals in en."
    previous = json.loads(recorder.calls[2][0].split("So far:\n", 1)[1])
    assert previous == {"count": 2, "seen": ["p1", "p2"]}


async def test_refine_validates_every_step(app: Brevia) -> None:
    wrong = iter([True])

    def respond(instructions: str, text: str) -> dict[str, Any]:
        answer = totals(instructions, text)
        if text == "p2" and next(wrong, False):
            answer["count"] = 9
        return answer

    recorder = Recorder(respond)
    with simulated(recorder.model()):
        result = await app.run(
            "test.strategy", Request(pieces=["p1", "p2"], strategy="refine")
        )

    assert len(recorder.retries) == 1
    assert "count differs" in recorder.retries[0]
    assert result == Totals(count=2, seen=["p1", "p2"])


async def test_strategies_stop_at_the_limits_of_the_run(app: Brevia) -> None:
    recorder = Recorder(summaries)
    with simulated(recorder.model()), pytest.raises(LimitExceeded):
        await app.run(
            "test.strategy",
            Request(pieces=[f"p{n}" for n in range(25)], strategy="map_reduce"),
        )

    assert len(recorder.calls) == 20


async def test_a_prompt_with_wrong_variables_fails_before_any_call(
    tmp_path: Path, app: Brevia
) -> None:
    async def wrong(request: Request, ctx: RunContext[Config]) -> Totals:
        return await refine(
            ctx,
            request.pieces,
            output_type=Totals,
            first_prompt=ctx.prompt("first"),
            refine_prompt=ctx.prompt("first"),  # has no {previous}
            values={"language": "en"},
        )

    app.register_activity(
        name="test.wrong",
        version="1",
        function=wrong,
        input_type=Request,
        output_type=Totals,
        config_type=Config,
        prompts={name: f"{name}.md" for name in PROMPTS},
    )
    recorder = Recorder(totals)
    with simulated(recorder.model()), pytest.raises(InvalidInput, match="Variables"):
        await app.run("test.wrong", Request(pieces=["a", "b"], strategy="refine"))

    assert recorder.calls == []


async def test_strategies_need_pieces() -> None:
    ctx: Any = object()
    prompt = PromptTemplate("p", "text", "test")
    with pytest.raises(ValueError, match="No pieces"):
        await refine(
            ctx, [], output_type=Totals, first_prompt=prompt, refine_prompt=prompt
        )
    with pytest.raises(ValueError, match="No pieces"):
        await map_reduce(
            ctx, [], output_type=Summary, map_prompt=prompt, combine_prompt=prompt
        )


async def test_map_reduce_stops_when_partials_cannot_be_combined_in_the_size(
    app: Brevia,
) -> None:
    recorder = Recorder(lambda _, text: {"summary": text * 10})
    with simulated(recorder.model()), pytest.raises(LimitExceeded) as raised:
        await app.run(
            "test.strategy",
            Request(pieces=["aaa", "bbb"], strategy="map_reduce", max_chars=40),
        )

    assert raised.value.details["max_chars"] == 40
    assert raised.value.details["outputs"] == 2
    assert len(recorder.calls) == 2


async def test_refine_of_one_piece_is_one_call(app: Brevia) -> None:
    recorder = Recorder(totals)
    with simulated(recorder.model()):
        result = await app.run(
            "test.strategy", Request(pieces=["p1"], strategy="refine")
        )

    assert result == Totals(count=1, seen=["p1"])
    assert len(recorder.calls) == 1


async def test_strategy_arguments_are_checked() -> None:
    ctx: Any = object()
    prompt = PromptTemplate("p", "text", "test")
    with pytest.raises(ValueError, match="previous"):
        await refine(
            ctx,
            ["a"],
            output_type=Totals,
            first_prompt=prompt,
            refine_prompt=prompt,
            values={"previous": "x"},
        )
    with pytest.raises(ValueError, match="positive"):
        await map_reduce(
            ctx,
            ["a"],
            output_type=Summary,
            map_prompt=prompt,
            combine_prompt=prompt,
            max_chars=0,
        )


async def test_map_reduce_never_sends_a_combination_over_the_size(
    app: Brevia,
) -> None:
    # Partials of about 150, 20 and 20 characters with a size of 100: the two short
    # ones fit together, the long one alone is over the size. No combination is sent.
    lengths = iter([130, 3, 3])  # at least 3: the validator refuses shorter ones
    recorder = Recorder(lambda *_: {"summary": "x" * next(lengths)})
    with simulated(recorder.model()), pytest.raises(LimitExceeded):
        await app.run(
            "test.strategy",
            Request(pieces=["a", "b", "c"], strategy="map_reduce", max_chars=100),
        )

    assert [kind for kind, _ in recorder.calls if "Combine" in kind] == []
    assert len(recorder.calls) == 3


async def test_map_reduce_of_one_partial_of_another_type_respects_the_size(
    app: Brevia,
) -> None:
    recorder = Recorder(lambda *_: {"count": 1, "seen": ["y" * 200]})
    with simulated(recorder.model()), pytest.raises(LimitExceeded):
        await app.run(
            "test.strategy",
            Request(pieces=["a"], strategy="map_reduce", partial=True, max_chars=100),
        )

    assert len(recorder.calls) == 1


@pytest.mark.parametrize("name", ["map_reduce", "refine"])
async def test_rules_of_the_project_follow_every_prompt(app: Brevia, name: str) -> None:
    respond = summaries if name == "map_reduce" else totals
    recorder = Recorder(respond)
    with simulated(recorder.model()):
        await app.run(
            "test.strategy",
            Request(pieces=["one", "two", "three"], strategy=name, rules="rules"),
        )

    assert len(recorder.calls) == (4 if name == "map_reduce" else 3)
    assert all(
        instructions.endswith("\n\nOnly facts about costs.")
        for instructions, _ in recorder.calls
    )


async def test_without_rules_the_prompts_are_unchanged(app: Brevia) -> None:
    recorder = Recorder(summaries)
    with simulated(recorder.model()):
        await app.run(
            "test.strategy", Request(pieces=["one", "two"], strategy="map_reduce")
        )

    assert [instructions for instructions, _ in recorder.calls] == [
        "Summarise this part in en.",
        "Summarise this part in en.",
        "Combine these summaries in en.",
    ]


@pytest.mark.parametrize("name", ["map_reduce", "refine"])
async def test_rules_with_variables_fail_before_any_call(
    app: Brevia, name: str
) -> None:
    recorder = Recorder(summaries)
    with simulated(recorder.model()), pytest.raises(InvalidInput):
        await app.run(
            "test.strategy",
            Request(pieces=["one", "two"], strategy=name, rules="bad_rules"),
        )

    assert recorder.calls == []
