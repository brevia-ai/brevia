"""Callers: the application that asks for an operation and its end user."""

from __future__ import annotations

import pytest

from brevia import AccessPolicy, Caller

pytestmark = pytest.mark.unit


def test_a_caller_has_a_name_and_an_optional_end_user() -> None:
    assert Caller("backend") == Caller("backend", end_user=None)
    assert Caller("backend", "user-7").end_user == "user-7"


@pytest.mark.parametrize(
    ("name", "end_user"),
    [("", None), ("   ", None), ("x" * 201, None), ("backend", ""), ("backend", " ")],
)
def test_blank_or_long_names_are_refused(name: str, end_user: str | None) -> None:
    with pytest.raises(ValueError, match="non-blank string"):
        Caller(name, end_user)


@pytest.mark.parametrize(
    ("name", "end_user"), [("backend\x00", None), ("backend", "user\x00")]
)
def test_names_with_nul_are_refused(name: str, end_user: str | None) -> None:
    # Recorded in PostgreSQL text columns, which refuse NUL.
    with pytest.raises(ValueError, match="NUL"):
        Caller(name, end_user)


# ---------- access policy ----------

OWNER, OTHER, ADMIN = Caller("owner"), Caller("other"), Caller("admin")


def test_per_caller_shows_each_caller_its_own_runs() -> None:
    policy = AccessPolicy(admins=frozenset({"admin"}))
    assert policy.sees(OWNER, "owner")
    assert not policy.sees(OTHER, "owner")
    assert not policy.sees(OWNER, None)  # a run of trusted code
    assert policy.sees(ADMIN, "owner")
    assert policy.sees(None, "owner")  # trusted code
    assert [policy.allows_everything(c) for c in (OWNER, ADMIN, None)] == [
        False,
        True,
        True,
    ]
    assert policy.visible_caller(OWNER) == "owner"
    assert policy.visible_caller(ADMIN) is None
    assert policy.visible_caller(None) is None


def test_shared_lets_every_caller_do_everything() -> None:
    policy = AccessPolicy(shared=True)
    assert policy.sees(OTHER, "owner")
    assert policy.allows_everything(OTHER)
    assert policy.visible_caller(OTHER) is None


def test_the_policy_is_read_from_its_settings() -> None:
    policy = AccessPolicy.from_names("per-caller", " admin , ops,")
    assert policy == AccessPolicy(admins=frozenset({"admin", "ops"}))
    assert AccessPolicy.from_names("shared", "").shared
    with pytest.raises(ValueError, match="per-caller"):
        AccessPolicy.from_names("open", "")
