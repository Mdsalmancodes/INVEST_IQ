"""Fake in-memory VerificationTokenStore-compatible Redis stand-in, and a
fake VerificationTokenStore itself, for unit-testing email verification and
password reset use cases without real Redis."""

from __future__ import annotations

from src.infrastructure.security.refresh_token_generator import (
    generate_refresh_token,
    hash_refresh_token,
)


class FakeVerificationTokenStore:
    """Implements the same interface as
    src.infrastructure.security.verification_token_store.VerificationTokenStore
    without needing a real Redis connection."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def issue(self, user_id: str) -> str:
        raw_token = generate_refresh_token()
        self._store[hash_refresh_token(raw_token)] = user_id
        return raw_token

    async def consume(self, raw_token: str) -> str | None:
        token_hash = hash_refresh_token(raw_token)
        user_id = self._store.get(token_hash)
        if user_id is not None:
            del self._store[token_hash]
        return user_id
