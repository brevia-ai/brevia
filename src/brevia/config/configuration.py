"""Resolution of the configuration of a run.

The configuration of a run is composed from, in order of precedence:

1. the project defaults: the defaults of the configuration schema, completed by the
   values of the project file;
2. the current customisation of the activity, stored in the database and limited to the
   fields the activity declares customisable;
3. the overrides of the request, limited to the fields the activity declares
   overridable.

Composition follows the schema: an absent field inherits; a present scalar or list
replaces; a nested model is composed field by field; a free mapping is replaced as a
whole, and so is a nested model that may be ``None``. ``None`` is a value only where
the schema allows it. Unknown fields are rejected even when the schema would ignore
them, and so are values incompatible with the schema. Inputs are never modified.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from brevia.errors import InvalidInput, OverrideNotAllowed, validation_details


def _nested_model(model_type: type[BaseModel], key: str) -> type[BaseModel] | None:
    """Model type of the field ``key``, if the field is a nested model."""
    field = model_type.model_fields.get(key)
    annotation = field.annotation if field is not None else None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def compose(
    base: Mapping[str, Any], override: Mapping[str, Any], model_type: type[BaseModel]
) -> dict[str, Any]:
    """Apply ``override`` on ``base`` following the schema of ``model_type``."""
    result = dict(base)
    for key, value in override.items():
        nested = _nested_model(model_type, key)
        current = result.get(key)
        if (
            nested is not None
            and isinstance(value, Mapping)
            and isinstance(current, Mapping)
        ):
            result[key] = compose(current, value, nested)
        else:
            result[key] = value
    return result


def override_paths(
    overrides: Mapping[str, Any], model_type: type[BaseModel], prefix: str = ""
) -> set[str]:
    """Dotted paths set by ``overrides``, descending only into nested models.

    A free mapping is a single value: its keys are not separate paths.
    """
    paths: set[str] = set()
    for key, value in overrides.items():
        nested = _nested_model(model_type, key)
        if nested is not None and isinstance(value, Mapping) and value:
            paths |= override_paths(value, nested, f"{prefix}{key}.")
        else:
            paths.add(prefix + key)
    return paths


def path_in_schema(model_type: type[BaseModel], path: str) -> bool:
    """Whether the dotted ``path`` names a field of the schema.

    Every segment but the last must be a nested model: a free mapping or a scalar has
    no addressable children.
    """
    head, _, rest = path.partition(".")
    if head not in model_type.model_fields:
        return False
    if not rest:
        return True
    nested = _nested_model(model_type, head)
    return nested is not None and path_in_schema(nested, rest)


def unknown_fields(
    model_type: type[BaseModel], data: Mapping[str, Any], prefix: str = ""
) -> list[str]:
    """Dotted paths of ``data`` that are not fields of the schema.

    Fields are matched by name or alias, and nested models are checked recursively.
    A schema that explicitly allows extra fields (``extra="allow"``) accepts any key.
    Brevia checks this itself because Pydantic ignores unknown fields by default, so
    a typo would otherwise pass unnoticed.
    """
    if model_type.model_config.get("extra") == "allow":
        return []
    fields = model_type.model_fields
    aliases = {field.alias: name for name, field in fields.items() if field.alias}
    unknown: list[str] = []
    for key, value in data.items():
        name = key if key in fields else aliases.get(key)
        if name is None:
            unknown.append(prefix + key)
            continue
        nested = _nested_model(model_type, name)
        if nested is not None and isinstance(value, Mapping):
            unknown += unknown_fields(nested, value, f"{prefix}{name}.")
    return unknown


def _field_values(model: BaseModel) -> dict[str, Any]:
    """Field values by name, nested models included.

    Unlike ``model_dump()``, it keeps fields excluded from serialisation and values
    with custom serialisers as they are.
    """
    return {
        name: _field_values(value) if isinstance(value, BaseModel) else value
        for name in type(model).model_fields
        for value in [getattr(model, name)]
    }


def path_allowed(path: str, allowed: Iterable[str]) -> bool:
    """A path is allowed if it, or one of its parents, is declared overridable."""
    parts = path.split(".")
    declared = frozenset(allowed)
    return any(".".join(parts[:end]) in declared for end in range(1, len(parts) + 1))


def _refused(
    values: Mapping[str, Any], model_type: type[BaseModel], allowed: Iterable[str]
) -> list[str]:
    """Paths set by ``values`` that no declared path allows."""
    declared = frozenset(allowed)
    return sorted(
        path
        for path in override_paths(values, model_type)
        if not path_allowed(path, declared)
    )


def check_customization(
    values: Mapping[str, Any],
    model_type: type[BaseModel],
    customizable: Iterable[str],
) -> None:
    """Reject customisations of fields that the activity does not declare customisable.

    Raises:
        InvalidInput: Unknown fields, or fields that may not be customised.
    """
    unknown = unknown_fields(model_type, values)
    if unknown:
        raise InvalidInput(
            "The customisation contains unknown fields", {"unknown": sorted(unknown)}
        )
    refused = _refused(values, model_type, customizable)
    if refused:
        raise InvalidInput(
            "The customisation sets fields that are not customisable",
            {"fields": refused},
        )


def without_paths(values: Mapping[str, Any], paths: Iterable[str]) -> dict[str, Any]:
    """``values`` without the dotted ``paths``; mappings left empty are removed."""
    result = dict(values)
    for path in paths:
        head, _, rest = path.partition(".")
        if head not in result:
            continue
        if not rest:
            del result[head]
        elif isinstance(result[head], Mapping):
            nested = without_paths(result[head], [rest])
            if nested:
                result[head] = nested
            else:
                del result[head]
    return result


def check_overrides(
    overrides: Mapping[str, Any],
    model_type: type[BaseModel],
    allowed: Iterable[str],
) -> None:
    """Reject overrides of fields that the activity does not declare overridable.

    Raises:
        OverrideNotAllowed: At least one field may not be overridden.
    """
    refused = _refused(overrides, model_type, allowed)
    if refused:
        raise OverrideNotAllowed(
            "The request overrides parameters that are not allowed",
            {"fields": refused},
        )


def resolve[ConfigT: BaseModel](
    config_type: type[ConfigT],
    defaults: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
    allowed: Iterable[str],
    customization: Mapping[str, Any] | None = None,
) -> ConfigT:
    """Validated configuration of one run.

    The customisation and then the overrides are applied on the complete defaults
    (the schema defaults completed by the project defaults), so that a partial value
    of a nested model keeps the defaults of its other fields. Customisations and
    overrides address fields by name; the project defaults may also use aliases.
    Which fields the customisation may set is checked by :func:`check_customization`.

    Args:
        config_type: Configuration schema of the activity.
        defaults: Project defaults for the activity.
        overrides: Overrides of the request.
        allowed: Dotted paths the request may override; a path allows its children.
        customization: Current customisation of the activity.

    Raises:
        OverrideNotAllowed: The request overrides a field that is not allowed.
        InvalidInput: The defaults or the overrides contain unknown fields, or the
            composed configuration does not match the schema.
    """
    overrides = overrides or {}
    customization = customization or {}
    check_overrides(overrides, config_type, allowed)
    unknown = (
        unknown_fields(config_type, defaults)
        + unknown_fields(config_type, customization)
        + unknown_fields(config_type, overrides)
    )
    if unknown:
        raise InvalidInput(
            "The configuration contains unknown fields", {"unknown": sorted(unknown)}
        )
    try:
        base = config_type.model_validate(defaults, by_alias=True, by_name=True)
        if customization:
            composed = compose(_field_values(base), customization, config_type)
            base = config_type.model_validate(composed, by_alias=True, by_name=True)
        if not overrides:
            return base
        composed = compose(_field_values(base), overrides, config_type)
        return config_type.model_validate(composed, by_alias=True, by_name=True)
    except ValidationError as exc:
        raise InvalidInput(
            "The configuration is not valid", validation_details(exc)
        ) from None
