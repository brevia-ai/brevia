"""Prompt templates with declared variables.

A template is plain text with ``{name}`` placeholders, where ``name`` is a lowercase
identifier. There are no loops, conditions or code. Rendering requires exactly the
variables of the template: missing and unknown variables are errors. Substituted values
are inserted as they are and never interpreted again as a template. Braces that are not
a placeholder, such as those of a JSON example, are left untouched.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from brevia.errors import InvalidInput, Unavailable

VARIABLE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


@dataclass(frozen=True)
class PromptTemplate:
    """A named prompt template.

    Attributes:
        name: Name used by the activity, for example ``"summary"``.
        text: Template text.
        source: Where the text comes from, for diagnosis (for example a file name).
    """

    name: str
    text: str
    source: str

    @cached_property
    def variables(self) -> frozenset[str]:
        """Names of the placeholders in the text."""
        return frozenset(VARIABLE.findall(self.text))

    @cached_property
    def sha256(self) -> str:
        """Fingerprint of the text, recorded in run snapshots."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def render(self, **values: object) -> str:
        """Text with every placeholder replaced by the string form of its value.

        Raises:
            InvalidInput: A variable is missing or unknown.
        """
        missing = sorted(self.variables - values.keys())
        unknown = sorted(values.keys() - self.variables)
        if missing or unknown:
            raise InvalidInput(
                f"Variables of prompt {self.name!r} do not match the template",
                {"missing": missing, "unknown": unknown},
            )
        return VARIABLE.sub(lambda match: str(values[match.group(1)]), self.text)


def load_prompt(name: str, path: Path) -> PromptTemplate:
    """Read a template from a UTF-8 text file.

    Raises:
        Unavailable: The file cannot be read.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Unavailable(
            f"Prompt {name!r} cannot be read from {path.name}",
            {"reason": type(exc).__name__},
        ) from exc
    return PromptTemplate(name=name, text=text, source=path.name)
