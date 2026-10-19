"""Configuration resolution: precedence, composition by schema, allowed overrides."""

from __future__ import annotations

import traceback
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from brevia.config.configuration import resolve
from brevia.errors import InvalidInput, OverrideNotAllowed

pytestmark = pytest.mark.unit


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    temperature: float | None = None
    max_tokens: int = 1000


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Model
    language: str = "it"
    tags: list[str] = ["a", "b"]
    labels: dict[str, str] = {}
    note: str | None = "default"


DEFAULTS = {
    "model": {"model": "openai:a", "max_tokens": 1200},
    "tags": ["x"],
    "labels": {"one": "1", "two": "2"},
}
ALLOWED = ["language", "model.temperature", "tags", "labels", "note"]


def test_absent_fields_inherit_and_present_values_replace() -> None:
    config = resolve(Config, DEFAULTS, {"language": "en"}, ALLOWED)
    assert config.language == "en"
    assert config.model.model == "openai:a"
    assert config.model.max_tokens == 1200
    assert config.tags == ["x"]


def test_nested_model_is_composed_field_by_field() -> None:
    config = resolve(Config, DEFAULTS, {"model": {"temperature": 0.2}}, ALLOWED)
    assert config.model == Model(model="openai:a", temperature=0.2, max_tokens=1200)


def test_lists_and_free_mappings_are_replaced_as_a_whole() -> None:
    config = resolve(Config, DEFAULTS, {"tags": [], "labels": {"three": "3"}}, ALLOWED)
    assert config.tags == []
    assert config.labels == {"three": "3"}


def test_none_is_a_value_where_the_schema_allows_it() -> None:
    assert resolve(Config, DEFAULTS, {"note": None}, ALLOWED).note is None


def test_override_not_declared_is_refused_with_its_path() -> None:
    with pytest.raises(OverrideNotAllowed) as caught:
        resolve(Config, DEFAULTS, {"model": {"model": "openai:b"}}, ALLOWED)
    assert caught.value.details == {"fields": ["model.model"]}


def test_a_declared_parent_allows_its_children() -> None:
    config = resolve(Config, DEFAULTS, {"model": {"model": "openai:b"}}, ["model"])
    assert config.model.model == "openai:b"


def test_unknown_or_incompatible_values_are_invalid_input() -> None:
    with pytest.raises(InvalidInput):
        resolve(Config, DEFAULTS, {"tags": "not a list"}, ALLOWED)
    with pytest.raises(InvalidInput):
        resolve(Config, {**DEFAULTS, "unknown": 1}, {}, ALLOWED)


def test_invalid_values_are_not_chained_to_the_error() -> None:
    value = "".join(["confidential ", "label"])  # not in the source of the test
    with pytest.raises(InvalidInput) as caught:
        resolve(Config, DEFAULTS, {"tags": value}, ALLOWED)
    assert caught.value.__cause__ is None
    assert value not in "".join(traceback.format_exception(caught.value))


def test_inputs_are_not_modified() -> None:
    defaults = {"model": {"model": "openai:a"}, "labels": {"one": "1"}}
    overrides = {"model": {"temperature": 0.5}}
    resolve(Config, defaults, overrides, ALLOWED)
    assert defaults == {"model": {"model": "openai:a"}, "labels": {"one": "1"}}
    assert overrides == {"model": {"temperature": 0.5}}


class Sub(BaseModel):
    x: int = 1
    y: int = 0


class WithNestedDefault(BaseModel):
    sub: Sub = Sub(x=5)
    lang: str = Field("it", alias="language")


def test_partial_override_keeps_the_schema_defaults_of_a_nested_model() -> None:
    config = resolve(WithNestedDefault, {}, {"sub": {"y": 9}}, ["sub"])
    assert config.sub == Sub(x=5, y=9)


def test_alias_in_defaults_and_name_in_overrides_are_both_accepted() -> None:
    assert resolve(WithNestedDefault, {"language": "en"}, {}, []).lang == "en"
    config = resolve(WithNestedDefault, {"language": "en"}, {"lang": "fr"}, ["lang"])
    assert config.lang == "fr"


class Plain(BaseModel):
    """A schema with Pydantic's default handling of extra fields (ignored)."""

    language: str = "it"
    sub: Sub = Sub()
    note: str = Field("schema", exclude=True)


@pytest.mark.parametrize(
    ("defaults", "overrides", "unknown"),
    [
        ({"langauge": "en"}, {}, ["langauge"]),
        ({}, {"sub": {"z": 1}}, ["sub.z"]),
    ],
)
def test_unknown_fields_are_refused_even_if_the_schema_ignores_them(
    defaults: dict[str, Any], overrides: dict[str, Any], unknown: list[str]
) -> None:
    with pytest.raises(InvalidInput) as caught:
        resolve(Plain, defaults, overrides, ["sub"])
    assert caught.value.details == {"unknown": unknown}


def test_fields_excluded_from_serialisation_keep_the_project_value() -> None:
    config = resolve(Plain, {"note": "project"}, {"language": "en"}, ["language"])
    assert config.note == "project"
