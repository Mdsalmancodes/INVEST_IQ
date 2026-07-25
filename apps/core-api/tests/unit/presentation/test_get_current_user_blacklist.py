"""Tests for get_current_user's Phase 8 token-blacklist check — real
JwtProvider-issued tokens, real get_current_user dependency (not
overridden, since it's the thing under test), with only
get_token_blacklist overridden to a fake so no real Redis connection is
needed. Matches test_rbac.py's exact "minimal FastAPI app + real HTTP
requests via ASGITransport" testing tier.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.config import get_settings
from src.domain.auth.entities import Role
from src.domain.auth.value_objects import UserId
from src.infrastructure.security.jwt_provider import JwtProvider
from src.presentation.dependencies.auth import get_current_user, get_token_blacklist


class FakeTokenBlacklist:
    def __init__(self, blacklisted_jtis: set[str] | None = None) -> None:
        self._blacklisted = blacklisted_jtis or set()

    async def is_blacklisted(self, jti: str) -> bool:
        return jti in self._blacklisted

    async def add(self, jti: str, ttl_seconds: int) -> None:
        self._blacklisted.add(jti)


def _build_test_app(blacklist: FakeTokenBlacklist) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_token_blacklist] = lambda: blacklist

    @app.get("/whoami", dependencies=[Depends(get_current_user)])
    async def whoami() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _issue_token() -> tuple[str, str]:
    """Issues via a JwtProvider built from the SAME real settings
    get_current_user's own get_jwt_provider dependency resolves (this
    test does not override get_jwt_provider) — tests/conftest.py sets
    JWT_SECRET before any test module imports src.config, so this
    resolves consistently in CI without a local .env file."""
    settings = get_settings()
    provider = JwtProvider(
        current_kid=settings.jwt_kid,
        current_secret=settings.jwt_secret.get_secret_value(),
        access_token_ttl_minutes=settings.jwt_access_token_ttl_minutes,
    )
    token = provider.issue_access_token(UserId.new(), Role.USER, token_version=0)
    claims = provider.verify_access_token(token)
    return token, claims.jti


class TestGetCurrentUserTokenBlacklist:
    async def test_a_valid_non_blacklisted_token_is_accepted(self) -> None:
        token, _ = _issue_token()
        app = _build_test_app(FakeTokenBlacklist())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

    async def test_a_blacklisted_token_is_rejected_with_401(self) -> None:
        token, jti = _issue_token()
        app = _build_test_app(FakeTokenBlacklist(blacklisted_jtis={jti}))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()
