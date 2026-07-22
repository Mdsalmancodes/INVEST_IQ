"""Value objects for the auth bounded context.

Per docs/architecture/03-backend-architecture-database-design.md §3.4 and
docs/architecture/08-coding-standards-git-roadmap.md §20.2: value objects are
plain dataclasses (not Pydantic — that's an infrastructure/presentation
concern), self-validating in __post_init__, so an invalid value cannot exist
as a constructed instance anywhere in the codebase.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from src.domain.auth.exceptions import InvalidEmailError, InvalidPasswordError

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# NIST 800-63B guidance (Document 6 §15.2): length-focused policy, not
# arbitrary complexity rules ("must contain a symbol" etc.).
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


@dataclass(frozen=True, slots=True)
class UserId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> UserId:
        return cls(uuid.uuid4())

    @classmethod
    def from_string(cls, raw: str) -> UserId:
        return cls(uuid.UUID(raw))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class Email:
    """Self-validating email value object. Normalizes to lowercase — Postgres's
    CITEXT column (Document 3 §8.1) also case-folds, but normalizing here means
    two `Email` instances constructed from differently-cased input compare
    equal in-process too, not just at the DB layer.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not _EMAIL_PATTERN.match(normalized):
            raise InvalidEmailError(f"'{self.value}' is not a valid email address")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PlaintextPassword:
    """A password as submitted by the user, BEFORE hashing.

    Self-validates length only (Document 6 §15.2's NIST-aligned policy).
    Common-password blocklist checking is an application-layer concern (it
    needs to consult a wordlist resource, which is an infrastructure
    dependency the domain layer must not import), not enforced here.
    """

    value: str

    def __post_init__(self) -> None:
        if len(self.value) < MIN_PASSWORD_LENGTH:
            raise InvalidPasswordError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
            )
        if len(self.value) > MAX_PASSWORD_LENGTH:
            raise InvalidPasswordError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")

    def __repr__(self) -> str:
        # Never let a plaintext password leak into a log line or traceback
        # via the default dataclass repr (Document 5 §14.1's redaction intent,
        # applied defensively here too — belt and suspenders).
        return "PlaintextPassword('[REDACTED]')"


@dataclass(frozen=True, slots=True)
class HashedPassword:
    """An Argon2 hash — opaque from the domain's perspective. The domain
    never knows or cares which hashing algorithm produced this string; that's
    infrastructure's job (src.infrastructure.security.password_hasher).
    """

    value: str

    def __repr__(self) -> str:
        return "HashedPassword('[REDACTED]')"
