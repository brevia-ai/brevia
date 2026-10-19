"""Authentication with JWT, compatible with the tokens of Brevia 0.15.

A token is signed with HS256 and carries two claims: ``user``, the name of the calling
application, and ``exp``, its expiry. Tokens issued by Brevia 0.15 with the same secret
stay valid. A valid token gives a :class:`~brevia.Caller`; what the caller may do is
decided by the access policy, not by the token.

Without a secret the authenticator cannot be created, unless authentication is turned
off explicitly with ``BREVIA_AUTH_DISABLED=true``: an installation that forgot the
secret does not start open.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from brevia.access.access import Caller
from brevia.errors import Unauthorized

logger = logging.getLogger(__name__)

ANONYMOUS = "anonymous"
"""Name of the caller of every request when authentication is disabled."""

ALGORITHM = "HS256"
"""Signature algorithm of the tokens, as in Brevia 0.15."""

RECOMMENDED_SECRET_BYTES = 32
"""Shortest secret recommended for HS256 (RFC 7518, section 3.2)."""


class AuthSettings(BaseSettings):
    """Authentication settings, read from ``BREVIA_*`` variables and ``.env``.

    Kept apart from :class:`~brevia.BreviaSettings`, so that ``brevia token create``
    needs no database settings.
    """

    model_config = SettingsConfigDict(
        env_prefix="BREVIA_",
        env_file=".env",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    tokens_secret: SecretStr | None = Field(
        default=None,
        description="Secret that signs and verifies the tokens; the ``TOKENS_SECRET`` "
        "of Brevia 0.15 keeps its tokens valid.",
    )
    tokens_users: str = Field(
        default="",
        description="Comma-separated names of the callers whose tokens are accepted; "
        "empty accepts any name, as ``TOKENS_USERS`` in Brevia 0.15.",
    )
    auth_disabled: bool = Field(
        default=False,
        description="Accept requests without a token: only for local development. "
        "Required to run without ``tokens_secret``.",
    )
    status_token: SecretStr | None = Field(
        default=None,
        description="Token of ``GET /status``, given as ``?token=`` or as a Bearer "
        "token, as ``STATUS_TOKEN`` in Brevia 0.15; accepted besides the token of a "
        "caller. Without it the endpoint needs the token of a caller, unless "
        "authentication is disabled.",
    )


def _users(value: str) -> frozenset[str]:
    return frozenset(name.strip() for name in value.split(",") if name.strip())


class Authenticator:
    """Verifies tokens and gives the caller they identify.

    Args:
        secret: Secret of the tokens; ``None`` only with ``disabled``.
        users: Names of the callers whose tokens are accepted; empty accepts any.
        disabled: Accept every request without verifying a token.

    Raises:
        ValueError: There is no secret and authentication is not disabled.
    """

    def __init__(
        self,
        secret: str | None,
        users: Iterable[str] = (),
        *,
        disabled: bool = False,
    ) -> None:
        if not disabled and not secret:
            raise ValueError(
                "A token secret is required: set BREVIA_TOKENS_SECRET, or "
                "BREVIA_AUTH_DISABLED=true to accept requests without a token"
            )
        self._secret = secret or ""
        self._users = frozenset(users)
        self.disabled = disabled
        if disabled:
            logger.warning("Authentication is disabled: requests need no token")
        elif secret is not None and len(secret.encode()) < RECOMMENDED_SECRET_BYTES:
            logger.warning(
                "The token secret is shorter than %d bytes: tokens are accepted, but "
                "a longer secret is recommended",
                RECOMMENDED_SECRET_BYTES,
            )

    @classmethod
    def from_settings(cls, settings: AuthSettings | None = None) -> Authenticator:
        """Authenticator configured by ``BREVIA_TOKENS_SECRET``,
        ``BREVIA_TOKENS_USERS`` and ``BREVIA_AUTH_DISABLED``.

        Raises:
            ValueError: There is no secret and authentication is not disabled.
        """
        settings = settings or AuthSettings()
        secret = settings.tokens_secret
        return cls(
            None if secret is None else secret.get_secret_value() or None,
            _users(settings.tokens_users),
            disabled=settings.auth_disabled,
        )

    def authenticate(self, token: str | None) -> Caller:
        """The caller identified by ``token``.

        When authentication is disabled, every request is the caller
        :data:`ANONYMOUS`, whatever its token: a caller, never trusted code, so that
        the access policy applies and local paths are refused.

        Raises:
            Unauthorized: The token is missing, expired, not signed with the secret,
                without a ``user`` that is a non-blank string, or of a caller not in
                the accepted names.
        """
        if self.disabled:
            return Caller(ANONYMOUS)
        if not token:
            raise Unauthorized("A token is required")
        try:
            with warnings.catch_warnings():
                # Short secrets of existing installations keep their tokens valid;
                # the warning is logged once, when the authenticator is created.
                warnings.simplefilter("ignore", jwt.InsecureKeyLengthWarning)
                payload: dict[str, Any] = jwt.decode(
                    token,
                    self._secret,
                    algorithms=[ALGORITHM],
                    options={"require": ["exp"]},
                )
        except jwt.InvalidTokenError:
            # The reason is not given: it would help to forge a token.
            raise Unauthorized("The token is not valid") from None
        user = payload.get("user")
        if not isinstance(user, str) or not user.strip():
            raise Unauthorized("The token is not valid")
        if self._users and user not in self._users:
            raise Unauthorized("The token is not valid")
        try:
            return Caller(user)
        except ValueError:  # a name too long
            raise Unauthorized("The token is not valid") from None


def create_token(user: str, minutes: int, secret: str) -> str:
    """A token for the caller ``user``, valid for ``minutes``, as Brevia 0.15 creates.

    Raises:
        ValueError: ``user`` is not a valid caller name, ``minutes`` is not positive,
            or ``secret`` is empty.
    """
    Caller(user)  # the same checks as a verified token
    if minutes < 1:
        raise ValueError("minutes must be at least 1")
    if not secret:
        raise ValueError("The token secret is empty")
    expiry = datetime.now(UTC) + timedelta(minutes=minutes)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", jwt.InsecureKeyLengthWarning)
        return jwt.encode({"user": user, "exp": expiry}, secret, algorithm=ALGORITHM)
