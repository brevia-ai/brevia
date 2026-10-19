"""Error catalogue: codes, HTTP statuses and public form."""

from __future__ import annotations

import pickle

import pytest

import brevia
from brevia.errors import BreviaError

pytestmark = pytest.mark.unit

CATALOGUE = {
    "InvalidInput": ("invalid_input", 422),
    "OverrideNotAllowed": ("override_not_allowed", 422),
    "Unauthorized": ("unauthorized", 401),
    "Forbidden": ("forbidden", 403),
    "NotFound": ("not_found", 404),
    "IdempotencyConflict": ("idempotency_conflict", 409),
    "VersionConflict": ("version_conflict", 412),
    "NotReady": ("not_ready", 409),
    "Busy": ("busy", 409),
    "Unsupported": ("unsupported", 422),
    "ProviderError": ("provider_error", 502),
    "FileTooLarge": ("file_too_large", 413),
    "Unavailable": ("unavailable", 503),
}
RUN_FAILURES = {
    "LimitExceeded": "limit_exceeded",
    "RunTimeout": "timeout",
    "OutputInvalid": "output_invalid",
    "ToolError": "tool_error",
    "ProviderError": "provider_error",
    "Cancelled": "cancelled",
    "InternalError": "internal",
}


@pytest.mark.parametrize(("name", "expected"), CATALOGUE.items())
def test_request_errors_match_the_catalogue(
    name: str, expected: tuple[str, int]
) -> None:
    error_type = getattr(brevia, name)
    assert issubclass(error_type, BreviaError)
    assert (error_type.code, error_type.http_status) == expected


@pytest.mark.parametrize(("name", "code"), RUN_FAILURES.items())
def test_run_failures_match_the_catalogue(name: str, code: str) -> None:
    assert getattr(brevia, name).code == code


def test_public_form_and_pickling_keep_the_details() -> None:
    error = brevia.ProviderError("Provider failed", {"status_code": 503})
    restored = pickle.loads(pickle.dumps(error))
    assert type(restored) is brevia.ProviderError
    assert restored.to_dict() == {
        "code": "provider_error",
        "message": "Provider failed",
        "details": {"status_code": 503},
        "retryable": True,
    }
