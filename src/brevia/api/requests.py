"""What every endpoint uses: the Brevia of the app, the caller, the error body."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Annotated, Any

from fastapi import Depends, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from brevia.access.access import Caller
from brevia.access.auth import Authenticator
from brevia.errors import InvalidInput
from brevia.runs.application import Brevia

REQUEST_ID_HEADER = "X-Request-ID"
"""Response header with the identifier of the request, also in error bodies and logs."""

EndUser = Annotated[
    str | None,
    Field(
        description="Opaque identifier of the end user the caller acts for, such as "
        "an id or a hash, never a name or an email address. Recorded for tracing; it "
        "grants no permission.",
        examples=["user-42"],
    ),
]
"""Field ``end_user`` of the body of a change: :attr:`brevia.Caller.end_user`."""


def get_brevia(request: Request) -> Brevia:
    """The Brevia of the app."""
    brevia: Brevia = request.app.state.brevia
    return brevia


_BEARER = HTTPBearer(
    auto_error=False,
    description="A token created with `brevia token create` (JWT, as in Brevia 0.15).",
)
"""Declares the Bearer token in the OpenAPI document, for the Authorize button of
``/docs``; the token is read and checked by :func:`get_caller`."""


class ErrorBody(BaseModel):
    """The body of every error of the HTTP API."""

    code: str
    message: str
    details: dict[str, Any]
    request_id: str


def get_caller(
    request: Request,
    _: Annotated[HTTPAuthorizationCredentials | None, Security(_BEARER)] = None,
) -> Caller:
    """The caller of the request, from its ``Authorization: Bearer`` token.

    Raises:
        Unauthorized: The token is missing or not valid.
    """
    authenticator: Authenticator = request.app.state.authenticator
    return authenticator.authenticate(bearer_token(request))


def acting_for(caller: Caller, end_user: str | None) -> Caller:
    """``caller`` acting for the ``end_user`` of the body of a change, if given.

    The caller vouches for the end user, as in :class:`~brevia.Caller`: it is
    recorded and grants no permission.

    Raises:
        InvalidInput: The end user is blank, too long or holds a NUL character.
    """
    if end_user is None:
        return caller
    try:
        return replace(caller, end_user=end_user)
    except ValueError:
        # Not the value: it would reach the error body and the logs.
        raise InvalidInput("The end user is not valid", {"field": "end_user"}) from None


CallerDep = Annotated[Caller, Depends(get_caller)]
"""Parameter of an endpoint that needs the caller: ``caller: CallerDep``."""

BreviaDep = Annotated[Brevia, Depends(get_brevia)]
"""Parameter of an endpoint that needs the Brevia of the app: ``brevia: BreviaDep``."""


def bearer_token(request: Request) -> str | None:
    """The token of ``Authorization: Bearer <token>``, if any."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


def request_id(request: Request) -> str:
    """Identifier of the request, set by the app for every request."""
    value: str = request.state.request_id
    return value


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """The body of every error: ``{code, message, details, request_id}``.

    ``headers`` are those of the original error, for example ``Allow`` of a 405.
    """
    ident = request_id(request)
    headers = {**(headers or {}), REQUEST_ID_HEADER: ident}
    if status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    body = {
        "code": code,
        "message": message,
        "details": details or {},
        "request_id": ident,
    }
    return JSONResponse(body, status_code=status, headers=headers)
