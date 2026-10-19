"""Prompt templates: declared variables, no re-interpretation, file loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from brevia.config.prompts import PromptTemplate, load_prompt
from brevia.errors import InvalidInput, Unavailable

pytestmark = pytest.mark.unit

TEMPLATE = PromptTemplate("summary", 'Summarise in {language}. Format: {"key": 1}', "t")


def test_render_replaces_only_declared_placeholders() -> None:
    assert TEMPLATE.variables == {"language"}
    assert TEMPLATE.render(language="English") == (
        'Summarise in English. Format: {"key": 1}'
    )


def test_values_are_not_interpreted_again_as_a_template() -> None:
    assert TEMPLATE.render(language="{language}").startswith("Summarise in {language}.")


@pytest.mark.parametrize(
    ("values", "missing", "unknown"),
    [({}, ["language"], []), ({"language": "it", "tone": "x"}, [], ["tone"])],
)
def test_missing_or_unknown_variables_are_errors(
    values: dict[str, str], missing: list[str], unknown: list[str]
) -> None:
    with pytest.raises(InvalidInput) as caught:
        TEMPLATE.render(**values)
    assert caught.value.details == {"missing": missing, "unknown": unknown}


def test_fingerprint_depends_only_on_the_text(tmp_path: Path) -> None:
    path = tmp_path / "summary.md"
    path.write_text(TEMPLATE.text, encoding="utf-8")
    loaded = load_prompt("other", path)
    assert loaded.sha256 == TEMPLATE.sha256
    assert loaded.source == "summary.md"


def test_unreadable_file_is_unavailable(tmp_path: Path) -> None:
    with pytest.raises(Unavailable):
        load_prompt("summary", tmp_path / "missing.md")
