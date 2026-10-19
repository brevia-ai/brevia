"""Brevia: a Python library for building AI applications.

The stable public API is what this module exports, together with what the documented
modules ``brevia.analysis``, ``brevia.tools``, ``brevia.api`` and ``brevia.testing``
export in their ``__all__``. Everything else is internal and may change without notice.
"""

from importlib.metadata import version

from brevia.access.access import AccessPolicy, Caller
from brevia.access.auth import Authenticator, AuthSettings, create_token
from brevia.config.customization import ConfigurationState, PromptRevision, PromptState
from brevia.config.prompts import PromptTemplate
from brevia.config.settings import BreviaSettings
from brevia.errors import (
    BreviaError,
    Busy,
    Cancelled,
    FileTooLarge,
    Forbidden,
    IdempotencyConflict,
    InternalError,
    InvalidInput,
    LimitExceeded,
    NotFound,
    NotReady,
    OutputInvalid,
    OverrideNotAllowed,
    ProviderError,
    RunTimeout,
    ToolError,
    Unauthorized,
    Unavailable,
    Unsupported,
    VersionConflict,
)
from brevia.files.documents import Document, Piece, Section, read_document, split
from brevia.files.files import FileRef, FileSource, FileStore, RunFiles
from brevia.jobs.handle import JobPage, JobState, RunHandle
from brevia.models import (
    ModelClient,
    ModelInfo,
    ModelSpec,
    Prices,
    RunLimits,
    Validator,
)
from brevia.runs.application import Brevia
from brevia.runs.context import RunContext
from brevia.runs.feedback import Correction, Feedback, FeedbackRequest
from brevia.runs.logs import configure_logging
from brevia.tools import Tool

__version__: str = version("brevia")

__all__ = [
    "AccessPolicy",
    "AuthSettings",
    "Authenticator",
    "Brevia",
    "BreviaError",
    "BreviaSettings",
    "Busy",
    "Caller",
    "Cancelled",
    "ConfigurationState",
    "Correction",
    "Document",
    "Feedback",
    "FeedbackRequest",
    "FileRef",
    "FileSource",
    "FileStore",
    "FileTooLarge",
    "Forbidden",
    "IdempotencyConflict",
    "InternalError",
    "InvalidInput",
    "JobPage",
    "JobState",
    "LimitExceeded",
    "ModelClient",
    "ModelInfo",
    "ModelSpec",
    "NotFound",
    "NotReady",
    "OutputInvalid",
    "OverrideNotAllowed",
    "Piece",
    "Prices",
    "PromptRevision",
    "PromptState",
    "PromptTemplate",
    "ProviderError",
    "RunContext",
    "RunFiles",
    "RunHandle",
    "RunLimits",
    "RunTimeout",
    "Section",
    "Tool",
    "ToolError",
    "Unauthorized",
    "Unavailable",
    "Unsupported",
    "Validator",
    "VersionConflict",
    "__version__",
    "configure_logging",
    "create_token",
    "read_document",
    "split",
]
