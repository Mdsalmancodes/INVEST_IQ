"""Tests for authenticate_websocket — real JwtProvider-issued tokens (same
convention as test_get_current_user_blacklist.py), real RedisClients
dataclass wrapping a fake Redis double for the session client (used by
TokenBlacklist), no real network/Redis connection needed.
"""

from __future__ import annotations

import pytest

from src.config import get_settings
from src.domain.auth.entities import Role
from src.domain.auth.value_objects import UserId
from src.infrastructure.persistence.redis.clients import RedisClients
from src.infrastructure.realtime.ws_auth import WebSocketAuthError, authenticate_websocket
from src.infrastructure.security.jwt_provider import JwtProvider


class FakeSessionRedis:
    """Minimal double for TokenBlacklist's 2 calls (set/exists)."""

    def __init__(self, blacklisted_jtis: set[str] | None = None) -> None:
        self._blacklisted = blacklisted_jtis or set()

    async def exists(self, key: str) -> int:
        jti = key.rsplit(":", 1)[-1]
        return 1 if jti in self._blacklisted else 0

    async def set(self, key: str, value: str, ex: int) -> None:  # pragma: no cover - unused here
        pass


def _build_provider() -> JwtProvider:
    settings = get_settings()
    return JwtProvider(
        current_kid=settings.jwt_kid,
        current_secret=settings.jwt_secret.get_secret_value(),
        access_token_ttl_minutes=settings.jwt_access_token_ttl_minutes,
    )


def _redis_clients_with_blacklist(blacklisted_jtis: set[str] | None = None) -> RedisClients:
    fake = FakeSessionRedis(blacklisted_jtis)
    return RedisClients(cache=fake, broker=fake, session=fake)  # type: ignore[arg-type]


class TestAuthenticateWebSocket:
    async def test_accepts_a_valid_non_blacklisted_token(self) -> None:
        provider = _build_provider()
        token = provider.issue_access_token(UserId.new(), Role.USER, token_version=0)

        claims = await authenticate_websocket(
            websocket=None,  # type: ignore[arg-type] - not used by this function
            token=token,
            jwt_provider=provider,
            redis_clients=_redis_clients_with_blacklist(),
        )

        assert claims.role == Role.USER

    async def test_rejects_a_missing_token(self) -> None:
        provider = _build_provider()
        with pytest.raises(WebSocketAuthError, match="Missing token"):
            await authenticate_websocket(
                websocket=None,  # type: ignore[arg-type]
                token=None,
                jwt_provider=provider,
                redis_clients=_redis_clients_with_blacklist(),
            )

    async def test_rejects_a_malformed_token(self) -> None:
        provider = _build_provider()
        with pytest.raises(WebSocketAuthError):
            await authenticate_websocket(
                websocket=None,  # type: ignore[arg-type]
                token="not-a-real-jwt",
                jwt_provider=provider,
                redis_clients=_redis_clients_with_blacklist(),
            )

    async def test_rejects_a_blacklisted_token(self) -> None:
        provider = _build_provider()
        token = provider.issue_access_token(UserId.new(), Role.USER, token_version=0)
        claims = provider.verify_access_token(token)

        with pytest.raises(WebSocketAuthError, match="revoked"):
            await authenticate_websocket(
                websocket=None,  # type: ignore[arg-type]
                token=token,
                jwt_provider=provider,
                redis_clients=_redis_clients_with_blacklist({claims.jti}),
            )
