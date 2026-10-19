"""Who asks for an operation, and what the access policy lets it do."""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_NAME_LENGTH = 200
"""Longest name of a caller or of an end user."""


@dataclass(frozen=True)
class Caller:
    """The application that asks for an operation, as identified by its token.

    ``name`` is the ``user`` field of the JWT: it names an application, not a person.
    ``end_user`` is an opaque identifier of the end user, given by a trusted caller
    (for example a backend with one token for all its users): an id or a hash, never
    a name or an email address. It is recorded for tracing and grants no permission.

    Operations that receive no caller (``caller=None``) are asked by trusted code in
    the process, such as scripts, workers and the command line: they record no caller.

    Raises:
        ValueError: ``name`` is blank, longer than :data:`MAX_NAME_LENGTH` or holds
            a NUL character, or ``end_user`` is given and is too.
    """

    name: str
    end_user: str | None = None

    def __post_init__(self) -> None:
        _check("name", self.name)
        if self.end_user is not None:
            _check("end_user", self.end_user)


def _check(field: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_NAME_LENGTH:
        raise ValueError(
            f"{field} must be a non-blank string of at most {MAX_NAME_LENGTH} "
            "characters"
        )
    if "\x00" in value:
        # PostgreSQL refuses NUL in text; replacing it would change the identity.
        raise ValueError(f"{field} must not contain NUL characters")


@dataclass(frozen=True)
class AccessPolicy:
    """Which runs a caller may read and act on, and who may change customisations.

    With ``per-caller`` (``shared=False``, the default), a caller sees only the runs
    it created; the callers named in ``admins`` see every run and may change the
    configuration and the prompts of the activities. With ``shared=True`` every caller
    may do everything, as with any valid token in Brevia 0.15. Trusted code without a
    caller may always do everything.

    Args:
        shared: Every caller may do everything.
        admins: Names of the callers that may do everything.
    """

    shared: bool = False
    admins: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_names(cls, policy: str, admins: str) -> AccessPolicy:
        """Policy from ``BREVIA_ACCESS_POLICY`` and ``BREVIA_ACCESS_ADMINS``.

        Raises:
            ValueError: ``policy`` is neither ``per-caller`` nor ``shared``.
        """
        if policy not in ("per-caller", "shared"):
            raise ValueError("The access policy must be 'per-caller' or 'shared'")
        names = frozenset(name.strip() for name in admins.split(",") if name.strip())
        return cls(shared=policy == "shared", admins=names)

    def allows_everything(self, caller: Caller | None) -> bool:
        """Whether ``caller`` may read and act on every run and change
        customisations."""
        return caller is None or self.shared or caller.name in self.admins

    def sees(self, caller: Caller | None, owner: str | None) -> bool:
        """Whether ``caller`` may read and act on a run created by ``owner``."""
        return self.allows_everything(caller) or (
            caller is not None and owner == caller.name
        )

    def visible_caller(self, caller: Caller | None) -> str | None:
        """The only owner whose runs ``caller`` may list, or ``None`` for every run."""
        return None if caller is None or self.allows_everything(caller) else caller.name
