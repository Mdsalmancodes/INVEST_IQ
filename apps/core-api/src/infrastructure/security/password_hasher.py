"""Argon2 password hashing — Document 6 §15.2 (password storage), using the
`argon2-cffi` library directly rather than reinventing password hashing
infrastructure, per the "prefer a mature library" implementation directive.

Note: Document 6 §15.2 named bcrypt in prose ("bcrypt, cost factor 12"), but
the founder's explicit Phase 2 instruction requires Argon2 specifically —
Argon2id (this module's choice) is the more modern, PHC-winning algorithm
and a strict security upgrade over bcrypt for the same purpose (password
hashing at rest). This is a same-purpose algorithm substitution within the
"Password Storage" requirement, not a change to the requirement itself, so
no ADR is raised for it — but it is noted here for traceability against
Document 6 §15.2's prose.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from src.domain.auth.value_objects import HashedPassword, PlaintextPassword


class Argon2PasswordHasher:
    """Cost parameters are argon2-cffi's own sensible defaults (time_cost=3,
    memory_cost=64MB, parallelism=4) — not hardcoded here as magic numbers,
    so they can be tuned via the library's own `PasswordHasher(...)`
    constructor arguments later without this class's interface changing.
    """

    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    def hash(self, password: PlaintextPassword) -> HashedPassword:
        return HashedPassword(self._hasher.hash(password.value))

    def verify(self, password: PlaintextPassword, hashed: HashedPassword) -> bool:
        try:
            self._hasher.verify(hashed.value, password.value)
        except VerifyMismatchError:
            return False
        return True

    def needs_rehash(self, hashed: HashedPassword) -> bool:
        """True if the stored hash was produced with older/weaker parameters
        than this hasher's current configuration — the application layer
        calls this on successful login to opportunistically re-hash with
        current parameters, per standard Argon2 rotation practice."""
        return self._hasher.check_needs_rehash(hashed.value)
