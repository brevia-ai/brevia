"""HTTP application: factory, lifespan, errors, caller and health endpoints."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import project_brevia
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from httpx2 import Response
from memory_store import MemoryStore
from pydantic import BaseModel, SecretStr

import brevia
from brevia import Brevia, NotFound, Unavailable, create_token
from brevia.access.auth import AuthSettings
from brevia.api import create_app
from brevia.api.requests import CallerDep

pytestmark = pytest.mark.unit

SECRET = "s" * 32


def settings(**values: Any) -> AuthSettings:
    """Explicit settings: the ``.env`` of the repository must not change the tests."""
    base: dict[str, Any] = {
        "tokens_secret": SecretStr(SECRET),
        "tokens_users": "",
        "auth_disabled": False,
        "status_token": None,
    }
    return AuthSettings(**(base | values))


class Echo(BaseModel):
    text: str


class Conflict(BaseModel):
    reason: str


def client_for(app_brevia: Brevia, **values: Any) -> TestClient:
    app = create_app(app_brevia, settings(**values))

    @app.get("/test/caller")
    async def caller(who: CallerDep) -> dict[str, str]:
        return {"name": who.name}

    @app.get("/test/not-found")
    async def missing() -> None:
        raise NotFound("No such thing", {"thing": "x"})

    @app.get("/test/crash")
    async def crash() -> None:
        raise RuntimeError("secret value in the message")

    @app.post("/test/echo")
    async def echo(body: Echo) -> Echo:
        return body

    @app.post(
        "/test/own-conflict",
        responses={409: {"model": Conflict, "description": "Own body"}},
    )
    async def own_conflict() -> JSONResponse:
        return JSONResponse({"reason": "taken"}, status_code=409)

    # Server exceptions are raised: an error that escapes the app fails the test.
    return TestClient(app)


@pytest.fixture
def client(tmp_path: Path, store: MemoryStore) -> Iterator[TestClient]:
    with client_for(project_brevia(tmp_path, store)) as test_client:
        yield test_client


def assert_error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    body: dict[str, Any] = response.json()
    assert body["code"] == code
    assert set(body) == {"code", "message", "details", "request_id"}
    assert body["request_id"] == response.headers["X-Request-ID"]
    return body


def test_every_response_has_a_request_id(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.json() == {"status": "ok"}
    uuid.UUID(response.headers["X-Request-ID"])
    assert (
        response.headers["X-Request-ID"]
        != client.get("/health/live").headers["X-Request-ID"]
    )


def test_the_app_starts_and_stops_brevia(tmp_path: Path, store: MemoryStore) -> None:
    with client_for(project_brevia(tmp_path, store)):
        assert store.events == ["start"]
    assert store.events == ["start", "stop"]


def test_ready_checks_the_database_now(client: TestClient, store: MemoryStore) -> None:
    assert client.get("/health/ready").json() == {"status": "ready"}
    store.fail.add("check")
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_status_is_compatible_with_brevia_015(
    client: TestClient, store: MemoryStore
) -> None:
    # As in Brevia 0.15: the token of a caller is required.
    assert_error(client.get("/status"), 401, "unauthorized")
    caller = {"Authorization": f"Bearer {create_token('monitor', 5, SECRET)}"}
    assert client.get("/status", headers=caller).json() == {"db_status": "OK"}
    assert client.head("/status", headers=caller).status_code == 200
    store.fail.add("check")
    response = client.get("/status", headers=caller)
    assert (response.status_code, response.json()) == (503, {"db_status": "KO"})


def test_status_is_open_with_authentication_disabled(
    tmp_path: Path, store: MemoryStore
) -> None:
    app = project_brevia(tmp_path, store)
    with client_for(app, tokens_secret=None, auth_disabled=True) as test_client:
        assert test_client.get("/status").json() == {"db_status": "OK"}


def test_status_token_is_required_when_set(tmp_path: Path, store: MemoryStore) -> None:
    app = project_brevia(tmp_path, store)
    with client_for(app, status_token=SecretStr("monitor")) as test_client:
        assert_error(test_client.get("/status"), 401, "unauthorized")
        assert_error(test_client.get("/status?token=wrong"), 401, "unauthorized")
        assert test_client.get("/status?token=monitor").json() == {"db_status": "OK"}
        headers = {"Authorization": "Bearer monitor"}
        assert test_client.get("/status", headers=headers).status_code == 200
        # The token of a caller is accepted too, as in Brevia 0.15.
        caller = {"Authorization": f"Bearer {create_token('bedita', 5, SECRET)}"}
        assert test_client.get("/status", headers=caller).status_code == 200


def test_health_needs_no_token(client: TestClient) -> None:
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


def test_caller_comes_from_the_bearer_token(client: TestClient) -> None:
    token = create_token("bedita", 5, SECRET)
    response = client.get("/test/caller", headers={"Authorization": f"Bearer {token}"})
    assert response.json() == {"name": "bedita"}


@pytest.mark.parametrize("header", [None, "Bearer", "Bearer not-a-token", "Basic abc"])
def test_a_missing_or_invalid_token_is_unauthorized(
    client: TestClient, header: str | None
) -> None:
    headers = {"Authorization": header} if header else {}
    response = client.get("/test/caller", headers=headers)
    assert_error(response, 401, "unauthorized")
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_with_authentication_disabled_every_caller_is_anonymous(
    tmp_path: Path, store: MemoryStore
) -> None:
    app = project_brevia(tmp_path, store)
    with client_for(app, tokens_secret=None, auth_disabled=True) as test_client:
        assert test_client.get("/test/caller").json() == {"name": "anonymous"}


def test_without_a_secret_the_app_is_not_created(
    tmp_path: Path, store: MemoryStore
) -> None:
    with pytest.raises(ValueError, match="BREVIA_TOKENS_SECRET"):
        client_for(project_brevia(tmp_path, store), tokens_secret=None)


def test_brevia_errors_keep_their_code_and_status(client: TestClient) -> None:
    body = assert_error(client.get("/test/not-found"), 404, "not_found")
    assert body["message"] == "No such thing"
    assert body["details"] == {"thing": "x"}


def test_unknown_paths_are_not_found(client: TestClient) -> None:
    assert_error(client.get("/nothing"), 404, "not_found")


def test_unexpected_errors_do_not_show_their_message(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    body = assert_error(client.get("/test/crash"), 500, "internal")
    assert body["message"] == "Internal error"
    assert "secret value" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_invalid_requests_give_locations_without_values(client: TestClient) -> None:
    response = client.post("/test/echo", json={"text": 12345678})
    body = assert_error(response, 422, "invalid_input")
    assert body["details"] == {
        "errors": [{"loc": ["body", "text"], "msg": "Input should be a valid string"}]
    }
    assert "12345678" not in response.text


def test_documentation_can_be_hidden(tmp_path: Path, store: MemoryStore) -> None:
    app = create_app(project_brevia(tmp_path, store), settings(), docs=False)
    with TestClient(app) as test_client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert_error(test_client.get(path), 404, "not_found")
    app = create_app(project_brevia(tmp_path, MemoryStore()), settings())
    with TestClient(app) as test_client:
        assert "/health/ready" in test_client.get("/openapi.json").json()["paths"]


async def test_check_needs_a_started_brevia(tmp_path: Path, store: MemoryStore) -> None:
    app = project_brevia(tmp_path, store)
    with pytest.raises(Unavailable, match="not started"):
        await app.check()
    async with app:
        await app.check()
        store.fail.add("check")
        with pytest.raises(Unavailable):
            await app.check()


def test_errors_keep_the_headers_of_the_original_error(client: TestClient) -> None:
    response = client.post("/health/live")
    assert_error(response, 405, "invalid_input")
    assert response.headers["Allow"] == "GET"


def test_the_status_token_is_hidden_in_the_access_log(
    tmp_path: Path, store: MemoryStore
) -> None:
    access = logging.getLogger("uvicorn.access")
    client_for(project_brevia(tmp_path, store))
    client_for(project_brevia(tmp_path, MemoryStore()))  # the filter is added once
    filters = [
        f
        for f in access.filters
        if isinstance(f, logging.Filter) and type(f).__name__ == "_StatusTokenFilter"
    ]
    assert len(filters) == 1
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5", "GET", "/status?a=1&token=monitor&b=2", "1.1", 200),
        None,
    )
    assert filters[0].filter(record)
    assert "monitor" not in record.getMessage()
    assert "/status?a=1&token=***&b=2" in record.getMessage()


def test_the_openapi_document_describes_the_real_errors_and_the_token(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["info"]["version"] == brevia.__version__
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    error = {"$ref": "#/components/schemas/ErrorBody"}
    caller = schema["paths"]["/test/caller"]["get"]
    assert caller["security"] == [{"HTTPBearer": []}]
    assert caller["responses"]["401"]["content"]["application/json"]["schema"] == error
    echo = schema["paths"]["/test/echo"]["post"]["responses"]["422"]
    assert echo["content"]["application/json"]["schema"] == error
    # The probes need no token and keep their own body.
    assert set(schema["paths"]["/health/live"]["get"]["responses"]) == {"200"}
    ready = schema["paths"]["/health/ready"]["get"]["responses"]["503"]
    assert "content" not in ready


def test_the_errors_declared_by_the_application_keep_their_schema(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()
    own = schema["paths"]["/test/own-conflict"]["post"]["responses"]["409"]
    assert own["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Conflict"
    }
    assert client.post("/test/own-conflict").json() == {"reason": "taken"}
