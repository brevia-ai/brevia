"""Values that PostgreSQL accepts in JSONB and TEXT columns.

PostgreSQL refuses non-finite numbers (``NaN``, infinities) in JSON and the NUL
character in both JSON and text. Values are checked before they are written, so that a
bad value is reported as such and not as an unavailable database.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_core import to_jsonable_python

NUL = "\x00"
REPLACEMENT = "\ufffd"


def storable_json(value: Any) -> Any:
    """``value`` as JSON data that PostgreSQL accepts.

    Raises:
        ValueError: A value has no JSON form, is not finite or contains a NUL
            character; the message names the reason only, never the value.
    """
    try:
        data = to_jsonable_python(value)
        json.dumps(data, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"no finite JSON form ({type(exc).__name__})") from None
    if _contains_nul(data):
        raise ValueError("contains a NUL character")
    return data


def _contains_nul(data: Any) -> bool:
    """Whether a string or key of JSON data contains a NUL character.

    The decoded strings are checked, not the serialised JSON, where the six characters
    of the escape sequence may also be ordinary text.
    """
    if isinstance(data, str):
        return NUL in data
    if isinstance(data, list):
        return any(_contains_nul(item) for item in data)
    if isinstance(data, dict):
        return any(
            _contains_nul(key) or _contains_nul(item) for key, item in data.items()
        )
    return False


def storable_text(text: str) -> bool:
    """Whether PostgreSQL accepts ``text`` in a TEXT column."""
    return NUL not in text


def without_nul(value: Any) -> Any:
    """JSON data or text with every NUL character replaced by U+FFFD."""
    if isinstance(value, str):
        return value.replace(NUL, REPLACEMENT)
    if isinstance(value, list):
        return [without_nul(item) for item in value]
    if isinstance(value, dict):
        return {without_nul(key): without_nul(item) for key, item in value.items()}
    return value


def recordable_json(value: Any) -> Any:
    """``value`` as JSON data for the record of a run.

    NUL characters, frequent in text extracted from documents, are replaced by U+FFFD
    instead of refusing the value: the record is a trace, not the value itself.

    Raises:
        ValueError: A value has no finite JSON form.
    """
    try:
        data = to_jsonable_python(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"no finite JSON form ({type(exc).__name__})") from None
    return storable_json(without_nul(data))
