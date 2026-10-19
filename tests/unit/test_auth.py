"""JWT authentication: tokens of Brevia 0.15, verification and the token command."""

from __future__ import annotations

import logging
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest

from brevia import (
    Authenticator,
    AuthSettings,
    Caller,
    FileSource,
    FileStore,
    InvalidInput,
    Unauthorized,
    create_token,
)
from brevia.cli import main

pytestmark = pytest.mark.unit

SECRET = "synthetic-secret-for-tests-only-0123456789"  # noqa: S105 - test data

# Created once with `brevia.tokens.create_token` of Brevia 0.15 (python-jose 3.4.0),
# with SECRET and the expiry fixed to 2100-01-01:
#   jwt.encode({"user": "brevia-015", "exp": datetime(2100, 1, 1)}, SECRET, "HS256")
TOKEN_OF_0_15 = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."  # noqa: S105 - signed with SECRET
    "eyJ1c2VyIjoiYnJldmlhLTAxNSIsImV4cCI6NDEwMjQ0NDgwMH0."
    "VG6tVieVc8C0MTGVycpWRNQ1a9h2jMWgrCPtOdQYcB4"
)


def signed(payload: dict[str, Any], secret: str = SECRET, alg: str = "HS256") -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", jwt.InsecureKeyLengthWarning)
        return jwt.encode(payload, secret, algorithm=alg)


def later(minutes: int = 10) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


def settings(**values: Any) -> AuthSettings:
    return AuthSettings(_env_file=None, **values)  # type: ignore[call-arg]


def test_a_token_of_brevia_0_15_stays_valid() -> None:
    assert Authenticator(SECRET).authenticate(TOKEN_OF_0_15) == Caller("brevia-015")


def test_a_created_token_has_the_claims_of_brevia_0_15() -> None:
    token = create_token("backend", 60, SECRET)
    payload = jwt.decode(token, options={"verify_signature": False})
    assert set(payload) == {"user", "exp"}
    assert payload["user"] == "backend"
    expiry = datetime.fromtimestamp(payload["exp"], UTC)
    assert later(59) < expiry <= later(60)
    assert Authenticator(SECRET).authenticate(token) == Caller("backend")


@pytest.mark.parametrize(
    "token",
    [
        signed({"user": "backend", "exp": later()}, secret="another-secret" * 3),
        signed({"user": "backend", "exp": later(-1)}),
        signed({"user": "backend"}),  # without expiry: accepted by Brevia 0.15
        signed({"exp": later()}),
        signed({"user": "", "exp": later()}),
        signed({"user": "   ", "exp": later()}),
        signed({"user": 42, "exp": later()}),
        signed({"user": "x" * 201, "exp": later()}),
        signed({"user": "backend\x00", "exp": later()}),  # refused by PostgreSQL
        signed({"user": "backend", "exp": later()}, alg="HS512"),
        "not-a-token",
        "",
        None,
    ],
)
def test_invalid_tokens_are_unauthorized(token: str | None) -> None:
    with pytest.raises(Unauthorized) as caught:
        Authenticator(SECRET).authenticate(token)
    assert caught.value.http_status == 401
    if token:
        assert token not in str(caught.value.to_dict())


def test_an_unsigned_token_is_unauthorized() -> None:
    token = jwt.encode({"user": "backend", "exp": later()}, None, algorithm="none")
    with pytest.raises(Unauthorized):
        Authenticator(SECRET).authenticate(token)


def test_only_listed_callers_are_accepted_when_a_list_is_given() -> None:
    authenticator = Authenticator.from_settings(
        settings(tokens_secret=SECRET, tokens_users=" backend , bedita,")
    )
    for user in ("backend", "bedita"):
        token = create_token(user, 5, SECRET)
        assert authenticator.authenticate(token) == Caller(user)
    with pytest.raises(Unauthorized):
        authenticator.authenticate(create_token("other", 5, SECRET))


def test_without_a_secret_authentication_must_be_disabled_explicitly() -> None:
    for values in ({}, {"tokens_secret": ""}):
        with pytest.raises(ValueError, match="BREVIA_AUTH_DISABLED"):
            Authenticator.from_settings(settings(**values))


def test_disabled_authentication_accepts_any_request(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="brevia.access.auth"):
        authenticator = Authenticator.from_settings(settings(auth_disabled=True))
    assert "Authentication is disabled" in caplog.text
    # A caller, not trusted code: the access policy applies and local paths are
    # refused (review of stage 4).
    assert authenticator.authenticate(None) == Caller("anonymous")
    assert authenticator.authenticate("anything") == Caller("anonymous")
    local = FileSource(name="a.txt", path=Path("/home/app/.env"))
    with pytest.raises(InvalidInput, match="trusted code"):
        FileStore(Path("files")).check_source(local, authenticator.authenticate(None))


def test_a_short_secret_is_accepted_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="brevia.access.auth"):
        authenticator = Authenticator("short")
    assert "shorter than 32 bytes" in caplog.text
    token = signed({"user": "backend", "exp": later()}, "short")
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # PyJWT would warn at each verification
        assert authenticator.authenticate(token) == Caller("backend")


@pytest.mark.parametrize(
    ("user", "minutes", "secret"), [("", 5, SECRET), ("a", 0, SECRET), ("a", 5, "")]
)
def test_invalid_token_requests_are_refused(
    user: str, minutes: int, secret: str
) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - three different messages
        create_token(user, minutes, secret)


def test_the_token_command_needs_only_the_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("BREVIA_DATABASE_URL", raising=False)
    monkeypatch.delenv("BREVIA_TOKENS_SECRET", raising=False)
    assert main(["token", "create", "--user", "backend"]) == 2
    assert "BREVIA_TOKENS_SECRET is not set" in capsys.readouterr().err
    monkeypatch.setenv("BREVIA_TOKENS_SECRET", SECRET)
    assert main(["token", "create", "--user", "backend", "--minutes", "5"]) == 0
    token = capsys.readouterr().out.strip()
    assert Authenticator(SECRET).authenticate(token) == Caller("backend")
    assert main(["token", "create", "--user", "backend", "--minutes", "0"]) == 2
    assert "minutes must be at least 1" in capsys.readouterr().err
