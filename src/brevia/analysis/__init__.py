"""Analysis of documents: strategies for texts longer than one model call.

A strategy runs the model on the pieces of a document (see :func:`brevia.split`) with
the prompts of the activity, and returns one validated output:

- :func:`map_reduce`: an output for each piece, then combined into one;
- :func:`refine`: an output from the first piece, updated with each following piece.

Each step is an ordinary ``generate`` call: validated and retried, recorded with the
run, within the limits of the run.

Ready activities built on them: :func:`summarize`, and :func:`extract` for the
extraction activities of a project.
"""

from brevia.analysis.extract import (
    EXTRACT_PROMPTS,
    ExtractConfig,
    ExtractRequest,
    extract,
    extract_document,
)
from brevia.analysis.strategies import map_reduce, refine
from brevia.analysis.summarize import (
    SUMMARIZE_PROMPTS,
    SummarizeConfig,
    SummarizeRequest,
    Summary,
    summarize,
    summarize_document,
)

__all__ = [
    "EXTRACT_PROMPTS",
    "SUMMARIZE_PROMPTS",
    "ExtractConfig",
    "ExtractRequest",
    "SummarizeConfig",
    "SummarizeRequest",
    "Summary",
    "extract",
    "extract_document",
    "map_reduce",
    "refine",
    "summarize",
    "summarize_document",
]
