"""Customisations of activities stored in the database: configuration and prompts.

A customisation changes the defaults of an activity for every new run, without a
release. The configuration is customised field by field, only on the paths the
activity declares ``customizable``; a prompt is customised as a whole, with exactly the
variables of its file. Every change of a prompt is kept in its history.

The states returned here are the public view of a customisation: what the project
defines, what the database changes and what a run without overrides would use.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from brevia.config.configuration import (
    check_customization,
    compose,
    path_allowed,
    path_in_schema,
    resolve,
    without_paths,
)
from brevia.config.prompts import PromptTemplate
from brevia.db.customizations import (
    StoredConfiguration,
    StoredPrompt,
    StoredRevision,
)
from brevia.db.values import storable_json, storable_text
from brevia.errors import InvalidInput, NotFound, Unavailable
from brevia.runs.activities import Activity


class ConfigurationState(BaseModel):
    """Configuration of an activity and its customisation.

    Attributes:
        activity: Name of the activity.
        defaults: Project defaults: the schema defaults completed by the project file.
        customization: Values set in the database, by field name.
        effective: Values a run without overrides uses; ``None`` when the stored
            customisation is no longer valid for the code (see ``problem``).
        problem: Why the stored customisation is not valid, if it is not.
        customizable: Dotted paths that may be customised.
        config_schema: JSON schema of the configuration.
        version: Version of the customisation, 0 when it was never changed; pass it
            as ``expected_version`` to detect concurrent changes.
        updated_by: Author of the last change, if given.
        updated_at: Time of the last change.
    """

    model_config = ConfigDict(frozen=True)

    activity: str
    defaults: dict[str, Any]
    customization: dict[str, Any]
    effective: dict[str, Any] | None
    problem: dict[str, Any] | None
    customizable: list[str]
    config_schema: dict[str, Any]
    version: int
    updated_by: str | None
    updated_at: datetime | None


class PromptState(BaseModel):
    """A prompt of an activity and its customisation.

    Attributes:
        activity: Name of the activity.
        name: Name of the prompt.
        file_text: Text of the prompt file.
        source: Name of the prompt file.
        customization: Customised text, or ``None`` when the file is used.
        effective: Text a new run uses.
        variables: Variables of the template, which a customised text must use.
        version: Version of the customisation, 0 when it was never changed.
        updated_by: Author of the last change, if given.
        updated_at: Time of the last change.
    """

    model_config = ConfigDict(frozen=True)

    activity: str
    name: str
    file_text: str
    source: str
    customization: str | None
    effective: str
    variables: list[str]
    version: int
    updated_by: str | None
    updated_at: datetime | None


class PromptRevision(BaseModel):
    """One change of a prompt: a customisation, or a reset to the file.

    Attributes:
        version: Version of the prompt after the change.
        operation: ``"customize"`` or ``"reset"``.
        text: Customised text; ``None`` for a reset.
        sha256: Fingerprint of the text; ``None`` for a reset.
        author: Author of the change, if given.
        created_at: Time of the change.
    """

    model_config = ConfigDict(frozen=True)

    version: int
    operation: Literal["customize", "reset"]
    text: str | None
    sha256: str | None
    author: str | None
    created_at: datetime


# ---------- configuration ----------


def configuration_state(
    activity: Activity, stored: StoredConfiguration
) -> ConfigurationState:
    """Public view of the configuration of ``activity``."""
    config_type = activity.config_type
    defaults = resolve(config_type, activity.defaults, None, ())
    effective: dict[str, Any] | None = None
    problem: dict[str, Any] | None = None
    try:
        effective = customized_config(activity, stored.values).model_dump(mode="json")
    except InvalidInput as exc:
        problem = {"message": exc.message, **exc.details}
    return ConfigurationState(
        activity=activity.name,
        defaults=defaults.model_dump(mode="json"),
        customization=dict(stored.values),
        effective=effective,
        problem=problem,
        customizable=sorted(activity.customizable),
        config_schema=config_type.model_json_schema(),
        version=stored.version,
        updated_by=stored.updated_by,
        updated_at=stored.updated_at,
    )


def customized_config(activity: Activity, values: Mapping[str, Any]) -> BaseModel:
    """Project defaults of ``activity`` with the customisation ``values`` applied.

    Raises:
        InvalidInput: ``values`` sets unknown or non-customisable fields, or the
            result does not match the schema.
    """
    check_customization(values, activity.config_type, activity.customizable)
    return resolve(
        activity.config_type, activity.defaults, None, (), customization=values
    )


def stored_customization(activity: Activity, values: Mapping[str, Any]) -> BaseModel:
    """Project defaults with the stored customisation, for a new run.

    Raises:
        Unavailable: The stored customisation is no longer valid for the code, for
            example after a field was removed or is no longer customisable.
    """
    try:
        return customized_config(activity, values)
    except InvalidInput as exc:
        raise Unavailable(
            f"Stored customisation of activity {activity.name!r} is not valid: "
            "change or reset it",
            exc.details,
        ) from None


def updated_values(
    activity: Activity, current: Mapping[str, Any], values: Mapping[str, Any]
) -> dict[str, Any]:
    """Customisation after setting ``values``; the other fields are kept.

    Raises:
        InvalidInput: The values or the resulting configuration are not valid.
    """
    check_customization(values, activity.config_type, activity.customizable)
    try:
        merged = storable_json(compose(current, values, activity.config_type))
    except ValueError as exc:
        raise InvalidInput(
            "The customisation contains values that cannot be stored",
            {"reason": str(exc)},
        ) from None
    customized_config(activity, merged)
    return dict(merged)


def reset_values(
    activity: Activity, current: Mapping[str, Any], fields: Iterable[str] | None
) -> dict[str, Any]:
    """Customisation without ``fields``, or empty when ``fields`` is ``None``.

    A field may be reset if it is customisable or if the current customisation sets
    it, so that a value left by an older version of the code (a field no longer
    customisable, renamed or removed) can be removed.

    Raises:
        InvalidInput: A field is not in the schema, or may not be reset.
    """
    if fields is None:
        return {}
    if isinstance(fields, str):
        raise InvalidInput("Fields to reset must be a list of paths, not a string")
    paths = sorted(set(fields))
    # A path set by the current customisation can always be removed, also when a
    # release renamed or removed the field.
    unknown = [
        p
        for p in paths
        if not path_in_schema(activity.config_type, p)
        and without_paths(current, [p]) == current
    ]
    if unknown:
        raise InvalidInput(
            "The reset names fields that are not in the configuration",
            {"unknown": unknown},
        )
    remaining = without_paths(current, paths)
    refused = [
        p
        for p in paths
        if not path_allowed(p, activity.customizable)
        and without_paths(current, [p]) == current
    ]
    if refused:
        raise InvalidInput(
            "The reset names fields that are not customisable", {"fields": refused}
        )
    return remaining


# ---------- prompts ----------


def template_of(activity: Activity, name: str) -> PromptTemplate:
    """File template of a prompt of ``activity``.

    Raises:
        NotFound: The activity does not declare this prompt.
    """
    try:
        return activity.prompts[name]
    except KeyError:
        raise NotFound(
            f"Prompt {name!r} is not declared by activity {activity.name!r}",
            {"activity": activity.name, "prompt": name},
        ) from None


def checked_prompt_text(template: PromptTemplate, text: str) -> str:
    """``text`` if it can replace ``template``: same variables, not blank.

    Raises:
        InvalidInput: The text is blank or its variables differ from the file.
    """
    if not text.strip():
        raise InvalidInput(f"Prompt {template.name!r} cannot be blank")
    if not storable_text(text):
        raise InvalidInput(f"Prompt {template.name!r} cannot contain NUL characters")
    candidate = PromptTemplate(template.name, text, "database")
    missing = sorted(template.variables - candidate.variables)
    unknown = sorted(candidate.variables - template.variables)
    if missing or unknown:
        raise InvalidInput(
            f"Customised prompt {template.name!r} must use exactly the variables of "
            "its file",
            {"missing": missing, "unknown": unknown},
        )
    return text


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_state(activity: Activity, name: str, stored: StoredPrompt) -> PromptState:
    """Public view of a prompt of ``activity``."""
    template = template_of(activity, name)
    return PromptState(
        activity=activity.name,
        name=name,
        file_text=template.text,
        source=template.source,
        customization=stored.text,
        effective=template.text if stored.text is None else stored.text,
        variables=sorted(template.variables),
        version=stored.version,
        updated_by=stored.updated_by,
        updated_at=stored.updated_at,
    )


def effective_prompts(
    activity: Activity, stored: Mapping[str, StoredPrompt]
) -> dict[str, tuple[PromptTemplate, int | None]]:
    """Template and customisation version of each prompt, for a new run.

    Customisations of prompts the activity no longer declares are ignored.

    Raises:
        Unavailable: A stored text no longer has the variables of its file.
    """
    result: dict[str, tuple[PromptTemplate, int | None]] = {}
    for name, template in activity.prompts.items():
        custom = stored.get(name)
        if custom is None or custom.text is None:
            result[name] = (template, None)
            continue
        try:
            checked_prompt_text(template, custom.text)
        except InvalidInput as exc:
            raise Unavailable(
                f"Stored customisation of prompt {name!r} of activity "
                f"{activity.name!r} is not valid: change or reset it",
                exc.details,
            ) from None
        result[name] = (PromptTemplate(name, custom.text, "database"), custom.version)
    return result


def revision(stored: StoredRevision) -> PromptRevision:
    return PromptRevision(
        version=stored.version,
        operation=stored.operation,
        text=stored.text,
        sha256=stored.sha256,
        author=stored.author,
        created_at=stored.created_at,
    )
