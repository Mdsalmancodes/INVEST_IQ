"""Unit tests for TokenBlacklist — uses a minimal in-memory fake
implementing only the two Redis methods TokenBlacklist actually calls
(set/exists), rather than pulling in a new fakeredis dependency for two
methods; matches this codebase's convention of small, purpose-built test
doubles (e.g. every FakeXRepository across the ai-service test suite).
"""

from __future__ import annotations

import time

from src.infrastructure.security.token_blacklist import TokenBlacklist


class FakeRedis:
    """Implements just enough of redis.asyncio.Redis's interface for
    TokenBlacklist: SET with an EX (expiry) option, and EXISTS."""

    def __init__(self) -> None:
        self._store: dict[str, float] = {}  # key -> expiry unix timestamp

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        expires_at = time.time() + ex if ex is not None else float("inf")
        self._store[key] = expires_at

    async def exists(self, key: str) -> int:
        expiry = self._store.get(key)
        if expiry is None:
            return 0
        if time.time() >= expiry:
            del self._store[key]
            return 0
        return 1


class TestTokenBlacklist:
    async def test_a_jti_that_was_never_added_is_not_blacklisted(self) -> None:
        blacklist = TokenBlacklist(FakeRedis())  # type: ignore[arg-type]

        assert await blacklist.is_blacklisted("some-jti") is False

    async def test_adding_a_jti_makes_it_blacklisted(self) -> None:
        blacklist = TokenBlacklist(FakeRedis())  # type: ignore[arg-type]

        await blacklist.add("some-jti", ttl_seconds=60)

        assert await blacklist.is_blacklisted("some-jti") is True

    async def test_an_empty_jti_is_never_blacklisted(self) -> None:
        # A token with no jti claim (issued before Phase 8's jti claim
        # existed) can never have been individually blacklisted.
        blacklist = TokenBlacklist(FakeRedis())  # type: ignore[arg-type]

        assert await blacklist.is_blacklisted("") is False

    async def test_add_with_zero_or_negative_ttl_is_a_no_op(self) -> None:
        blacklist = TokenBlacklist(FakeRedis())  # type: ignore[arg-type]

        await blacklist.add("some-jti", ttl_seconds=0)

        assert await blacklist.is_blacklisted("some-jti") is False

    async def test_an_expired_blacklist_entry_is_treated_as_not_blacklisted(self) -> None:
        blacklist = TokenBlacklist(FakeRedis())  # type: ignore[arg-type]

        await blacklist.add("some-jti", ttl_seconds=1)
        time.sleep(1.1)

        assert await blacklist.is_blacklisted("some-jti") is False
