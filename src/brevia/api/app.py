"""The HTTP application: one FastAPI app with the endpoints of Brevia.

:func:`create_app` builds it around a :class:`~brevia.Brevia` with its activities
registered. The app starts and stops Brevia with its own lifespan, turns the token of
each request into the :class:`~brevia.Caller` passed to the operations, and answers
every error with the same body, ``{code, message, details, request_id}``. An
application adds its own endpoints to the same app.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from brevia import __version__
from brevia.access.auth import Authenticator, AuthSettings
from brevia.api.requests import REQUEST_ID_HEADER, ErrorBody, error_response, request_id
from brevia.api.routes import activities, configurations, health, runs
from brevia.errors import BreviaError
from brevia.runs.application import Brevia

logger = logging.getLogger(__name__)

_HTTP_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    413: "file_too_large",
}
"""Error codes of the HTTP errors raised by the framework, outside Brevia."""


def create_app(
    brevia: Brevia, settings: AuthSettings | None = None, *, docs: bool = True
) -> FastAPI:
    """The HTTP application of ``brevia``.

    Register the activities before creating the app: the app starts Brevia when it
    starts and stops it when it stops. Run it with an ASGI server, for example
    ``uvicorn myproject.api:app``; add the endpoints of the application to it.

    Args:
        brevia: The Brevia of the application, not started.
        settings: Authentication settings; by default read from ``BREVIA_*``
            variables and ``.env``.
        docs: Serve the interactive documentation (``/docs``, ``/redoc``) and the
            OpenAPI document (``/openapi.json``); ``False`` hides them.

    Raises:
        ValueError: There is no token secret and authentication is not disabled.
    """
    settings = settings or AuthSettings()
    authenticator = Authenticator.from_settings(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await brevia.start()
        try:
            yield
        finally:
            await brevia.stop()

    app = FastAPI(
        title="Brevia",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.brevia = brevia
    app.state.authenticator = authenticator
    token = settings.status_token
    app.state.status_token = None if token is None else token.get_secret_value()

    app.middleware("http")(_set_request_id)
    app.add_exception_handler(BreviaError, _brevia_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.include_router(health.router)
    app.include_router(activities.router)
    app.include_router(runs.router)
    app.include_router(configurations.configurations)
    app.include_router(configurations.prompts)
    _hide_status_token(logging.getLogger("uvicorn.access"))
    app.openapi = lambda: _openapi(app)  # type: ignore[method-assign]
    return app


_ERROR_REF = {"$ref": "#/components/schemas/ErrorBody"}
_OWN_BODIES = {("/health/ready", "503"), ("/status", "503")}
"""Error answers with a body of their own: the probes and the status of Brevia 0.15."""


def _openapi(app: FastAPI) -> dict[str, Any]:
    """The OpenAPI document, with the error body that the app really answers.

    FastAPI describes validation errors as ``{"detail": [...]}`` and knows nothing of
    the error handlers: those answers, and the error answers declared without a schema,
    are described as ``ErrorBody``, and every endpoint that needs a token may answer
    ``401``. An error answer declared with its own schema, for example by an endpoint
    of the application, is kept as declared.
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        description=app.description,
    )
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components["ErrorBody"] = ErrorBody.model_json_schema()
    for path, item in schema.get("paths", {}).items():
        for operation in item.values():
            responses = operation.setdefault("responses", {})
            if operation.get("security"):
                responses.setdefault("401", {"description": "Missing or invalid token"})
            for status, answer in responses.items():
                if not status.isdigit() or int(status) < 400:
                    continue
                if (path, status) in _OWN_BODIES:
                    continue
                content = answer.get("content")
                if content is None:
                    answer["content"] = {"application/json": {"schema": _ERROR_REF}}
                elif _is_validation_error(content):
                    answer["description"] = "The request is not valid"
                    answer["content"] = {"application/json": {"schema": _ERROR_REF}}
    if _VALIDATION_REF not in json.dumps(schema.get("paths", {})):
        for name in ("HTTPValidationError", "ValidationError"):
            components.pop(name, None)
    app.openapi_schema = schema
    return schema


_VALIDATION_REF = "#/components/schemas/HTTPValidationError"


def _is_validation_error(content: dict[str, Any]) -> bool:
    """Whether ``content`` is the validation error that FastAPI adds by itself."""
    media: dict[str, Any] = content.get("application/json", {})
    return bool(media.get("schema") == {"$ref": _VALIDATION_REF})


async def _set_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    # Always generated: a value chosen by the client would reach the logs.
    request.state.request_id = str(uuid.uuid4())
    try:
        response = await call_next(request)
    except Exception as exc:
        # Handled here and not by an exception handler: Starlette re-raises after
        # its handler, and the server would then log the message and the frames,
        # which may hold data. Only the type is logged.
        logger.error(
            "Unexpected error: %s %s (%s)",
            request.method,
            request.url.path,
            type(exc).__name__,
            extra={"request_id": request.state.request_id},
        )
        return error_response(request, 500, "internal", "Internal error")
    response.headers[REQUEST_ID_HEADER] = request.state.request_id
    return response


async def _brevia_error(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, BreviaError):  # registered for BreviaError only
        raise exc
    if exc.http_status >= 500:
        logger.error(
            "Request failed: %s %s (%s)",
            request.method,
            request.url.path,
            exc.code,
            extra={"request_id": request_id(request)},
        )
    return error_response(
        request, exc.http_status, exc.code, exc.message, dict(exc.details)
    )


async def _validation_error(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RequestValidationError):
        raise exc
    # Locations and messages only: the values may hold the input of the caller.
    errors = [
        {"loc": [str(part) for part in error.get("loc", ())], "msg": error.get("msg")}
        for error in exc.errors()
    ]
    return error_response(
        request, 422, "invalid_input", "The request is not valid", {"errors": errors}
    )


async def _http_error(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    if exc.status_code >= 500:
        code = "internal"
    else:
        code = _HTTP_CODES.get(exc.status_code, "invalid_input")
    return error_response(
        request, exc.status_code, code, str(exc.detail), headers=exc.headers
    )


_STATUS_TOKEN = re.compile(r"([?&]token=)[^&\s]*")


class _StatusTokenFilter(logging.Filter):
    """Hides the value of ``?token=`` in the access log of uvicorn.

    The token of ``/status`` may come in the query, as in Brevia 0.15; the access log
    writes the full path with its query, as the third argument of each record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            path = _STATUS_TOKEN.sub(r"\1***", args[2])
            record.args = (*args[:2], path, *args[3:])
        return True


def _hide_status_token(access_logger: logging.Logger) -> None:
    if not any(isinstance(f, _StatusTokenFilter) for f in access_logger.filters):
        access_logger.addFilter(_StatusTokenFilter())
