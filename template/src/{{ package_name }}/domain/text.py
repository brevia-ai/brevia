"""Text preparation and checks."""

import re

_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """The text with runs of spaces and line breaks reduced to one space."""
    return _SPACES.sub(" ", text).strip()


def word_count(text: str) -> int:
    return len(text.split())


def length_problems(text: str, max_words: int) -> list[str]:
    """Problems of a generated text, sent back to the model for a new attempt."""
    words = word_count(text)
    return [f"the summary has {words} words, at most {max_words}"] if words > max_words else []
