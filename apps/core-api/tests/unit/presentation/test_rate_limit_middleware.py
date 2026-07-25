"""Tests for RateLimitMiddleware — a minimal FastAPI app with the
middleware attached, exercised via real HTTP requests (matching
test_rbac.py's tier), with a fake Redis client injected via monkeypatching
get_redis_clients (the middleware resolves its own Redis client per-
request rather than through FastAPI's Depends() system, since
BaseHTTPMiddleware.dispatch() is not itself a route handler that
participates in dependency injection).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from src.presentation import rate_limit_middleware as rlm


class FakeRedisClients:
    def __init__(self, session: object) -> None:
        self.session = session


class FakeCountingRedis:
    """Increments an in-memory counter — lets tests exercise the actual
    over-limit 429 path without a real Redis connection."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass

    async def ttl(self, key: str) -> int:
        return 30


class FakeUnreachableRedis:
    """Simulates Redis being completely unreachable — every call raises,
    exercising the middleware's fail-open path."""

    async def incr(self, key: str) -> int:
        raise RedisConnectionError("simulated connection failure")

    async def expire(self, key: str, seconds: int) -> None:
        raise RedisConnectionError("simulated connection failure")

    async def ttl(self, key: str) -> int:
        raise RedisConnectionError("simulated connection failure")


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(rlm.RateLimitMiddleware)

    @app.get("/some-route")
    async def some_route() -> dict[str, str]:
        return {"status": "ok"}

    return app


@pytest.fixture
def app() -> FastAPI:
    return _build_test_app()


class TestRateLimitMiddlewareFailsOpen:
    async def test_requests_succeed_when_redis_is_completely_unreachable(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            rlm, "get_redis_clients", lambda: FakeRedisClients(FakeUnreachableRedis())
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/some-route")
        assert response.status_code == 200


class TestRateLimitMiddlewareEnforcement:
    async def test_requests_under_the_limit_succeed(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            rlm, "get_redis_clients", lambda: FakeRedisClients(FakeCountingRedis())
        )
        monkeypatch.setattr(rlm.get_settings(), "rate_limit_requests_per_window", 5)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/some-route")
        assert response.status_code == 200

    async def test_exceeding_the_limit_returns_429_with_retry_after(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_redis = FakeCountingRedis()
        monkeypatch.setattr(rlm, "get_redis_clients", lambda: FakeRedisClients(fake_redis))
        monkeypatch.setattr(rlm.get_settings(), "rate_limit_requests_per_window", 2)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/some-route")
            await client.get("/some-route")
            response = await client.get("/some-route")

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert "Retry-After" in response.headers


class TestRateLimitMiddlewareExemptPaths:
    async def test_health_path_bypasses_rate_limiting_entirely(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app = FastAPI()
        app.add_middleware(rlm.RateLimitMiddleware)

        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        # Deliberately do NOT patch get_redis_clients — if the exemption
        # check didn't short-circuit before touching Redis, this would
        # raise/fail-open through a real connection attempt instead of
        # returning immediately.
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
