"""Health endpoints: liveness and readiness probes, and ``/status`` of Brevia 0.15.

The probes need no token: containers and load balancers call them. ``/status`` needs a
token as in Brevia 0.15: the token of a caller, or its own ``BREVIA_STATUS_TOKEN``.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from brevia.access.auth import Authenticator
from brevia.api.requests import bearer_token, error_response
from brevia.errors import Unauthorized, Unavailable

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    """The process answers."""
    return {"status": "ok"}


@router.get("/health/ready", responses={503: {"description": "Not ready"}})
async def ready(request: Request) -> JSONResponse:
    """Brevia is started and its database answers with the migrated schema.

    The reason of a failure is logged by Brevia, not returned: the endpoint is open.
    """
    try:
        await request.app.state.brevia.check()
    except Unavailable:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ready"})


@router.head("/status", include_in_schema=False)
@router.get(
    "/status",
    responses={
        401: {"description": "Neither a caller token nor the status token"},
        503: {"description": "Database down"},
    },
)
async def status(request: Request, token: str | None = None) -> JSONResponse:
    """``{"db_status": "OK"}`` or ``"KO"``, as in Brevia 0.15.

    It needs the token of a caller as a Bearer token, or ``BREVIA_STATUS_TOKEN``, when
    set, as ``?token=`` or as a Bearer token; with authentication disabled it is open.
    """
    expected: str | None = request.app.state.status_token
    given = token or bearer_token(request) or ""
    status_token = expected is not None and hmac.compare_digest(
        given.encode(), expected.encode()
    )
    if not status_token:
        authenticator: Authenticator = request.app.state.authenticator
        try:
            authenticator.authenticate(bearer_token(request))
        except Unauthorized:
            return error_response(
                request,
                401,
                "unauthorized",
                "A caller token or the status token is required",
            )
    try:
        await request.app.state.brevia.check()
    except Unavailable:
        return JSONResponse({"db_status": "KO"}, status_code=503)
    return JSONResponse({"db_status": "OK"})
