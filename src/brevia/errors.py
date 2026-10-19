"""Error catalogue shared by the Python API and the HTTP API.

Every error has a stable ``code``. The same code is returned over HTTP as
``{code, message, details, request_id}``; a failed run reports
``{code, message, details, retryable}``. Messages and details must never contain
secrets, credentials or document contents.
"""

from __future__ import annotations

from typing import Any, ClassVar, Self

from pydantic import ValidationError


class BreviaError(Exception):
    """Base class of every error raised by Brevia.

    Args:
        message: Human-readable description, safe to show to the caller.
        details: Structured, JSON-serialisable information about the error.
        retryable: Whether repeating the operation may succeed; the default of the
            error class when not given.
    """

    code: ClassVar[str] = "internal"
    http_status: ClassVar[int] = 500
    default_retryable: ClassVar[bool] = False

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details or {})
        self.retryable = self.default_retryable if retryable is None else retryable

    def __reduce__(
        self,
    ) -> tuple[Any, tuple[type[Self], str, dict[str, Any], bool]]:
        # Keep details and retryability when pickled, for example by a job engine.
        return _rebuild, (type(self), self.message, self.details, self.retryable)

    def to_dict(self) -> dict[str, Any]:
        """Public form of the error, as reported for a failed run."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }


# ---------- request errors ----------


class InvalidInput(BreviaError):
    """The input or the configuration of a request is not valid."""

    code = "invalid_input"
    http_status = 422


class OverrideNotAllowed(BreviaError):
    """The request overrides a parameter that the activity does not allow."""

    code = "override_not_allowed"
    http_status = 422


class Unauthorized(BreviaError):
    """The access token is missing or not valid."""

    code = "unauthorized"
    http_status = 401


class Forbidden(BreviaError):
    """The access policy denies the operation."""

    code = "forbidden"
    http_status = 403


class NotFound(BreviaError):
    """The resource does not exist or is not visible to the caller."""

    code = "not_found"
    http_status = 404


class IdempotencyConflict(BreviaError):
    """The same idempotency key was used for a different request."""

    code = "idempotency_conflict"
    http_status = 409


class VersionConflict(BreviaError):
    """A concurrent change modified the configuration or the prompt first."""

    code = "version_conflict"
    http_status = 412


class NotReady(BreviaError):
    """The result was requested before the run finished."""

    code = "not_ready"
    http_status = 409


class Busy(BreviaError):
    """The conversation already has a message being processed."""

    code = "busy"
    http_status = 409


class Unsupported(BreviaError):
    """The model, the adapter or a reader does not offer the requested capability."""

    code = "unsupported"
    http_status = 422


class ProviderError(BreviaError):
    """The model provider returned an error."""

    code = "provider_error"
    http_status = 502
    default_retryable = True


class FileTooLarge(BreviaError):
    """The file exceeds the allowed size."""

    code = "file_too_large"
    http_status = 413


class Unavailable(BreviaError):
    """The database or the configuration is not available."""

    code = "unavailable"
    http_status = 503
    default_retryable = True


# ---------- run failures ----------
# A request whose run failed answers 422, not a server error: clients and proxies repeat
# 5xx answers by themselves, and every repetition would call the model again.


class LimitExceeded(BreviaError):
    """A run limit (requests, tool calls or tokens) was reached."""

    code = "limit_exceeded"
    http_status = 422


class RunTimeout(BreviaError):
    """The run exceeded its maximum duration."""

    code = "timeout"
    http_status = 422


class OutputInvalid(BreviaError):
    """The model output did not pass validation within the allowed attempts."""

    code = "output_invalid"
    http_status = 422


class ToolError(BreviaError):
    """A tool failed while the run was using it."""

    code = "tool_error"
    http_status = 422


class Cancelled(BreviaError):
    """The run was cancelled."""

    code = "cancelled"
    http_status = 422


class InternalError(BreviaError):
    """An unexpected error. Its details never expose the original exception."""

    code = "internal"


def _rebuild(
    error_type: type[BreviaError],
    message: str,
    details: dict[str, Any],
    retryable: bool,
) -> BreviaError:
    return error_type(message, details, retryable=retryable)


def _error_classes(base: type[BreviaError]) -> dict[str, type[BreviaError]]:
    found: dict[str, type[BreviaError]] = {}
    for error_type in base.__subclasses__():
        found.setdefault(error_type.code, error_type)
        found.update(
            (code, t)
            for code, t in _error_classes(error_type).items()
            if code not in found
        )
    return found


def error_from_dict(data: dict[str, Any]) -> BreviaError:
    """The error recorded by :meth:`BreviaError.to_dict`; unknown codes become
    :class:`InternalError` with the recorded message."""
    error_type = _error_classes(BreviaError).get(data.get("code", ""), InternalError)
    return error_type(
        str(data.get("message", "")),
        dict(data.get("details") or {}),
        retryable=data.get("retryable"),
    )


def validation_details(exc: ValidationError) -> dict[str, Any]:
    """Details of a Pydantic validation error, without the input values.

    Input values and error contexts are left out: they may contain user data.
    """
    return {
        "errors": exc.errors(
            include_url=False, include_input=False, include_context=False
        )
    }


def cause_types(exc: BaseException, limit: int = 6) -> list[str]:
    """Type names along the chain of causes of ``exc``, outermost first.

    Only the names: messages of dependencies may contain request data or credentials.
    """
    names: list[str] = []
    current: BaseException | None = exc
    while current is not None and len(names) < limit:
        names.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    return names
