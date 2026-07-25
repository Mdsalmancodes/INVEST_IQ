"""Tests for POST /api/v1/auth/logout's Phase 8 change — now requires
authentication (previously anonymous) and blacklists the presented access
token's jti. Uses the real app with get_current_user, get_logout_use_case,
and get_token_blacklist overridden (the last two so no real Postgres/Redis
connection is needed at this unit-test tier).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.application.auth.logout_use_case import LogoutUseCase
from src.domain.auth.entities import Role
from src.domain.auth.value_objects import UserId
from src.main import app
from src.presentation.dependencies.auth import CurrentUser, get_current_user
from src.presentation.dependencies.use_cases import get_logout_use_case


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestLogoutRequiresAuthentication:
    async def test_logout_without_a_bearer_token_is_rejected(self, client: AsyncClient) -> None:
        app.dependency_overrides.pop(get_current_user, None)

        response = await client.post(
            "/api/v1/auth/logout", json={"refresh_token": "some-refresh-token"}
        )

        assert response.status_code == 401

    async def test_logout_with_a_valid_token_calls_the_use_case_with_jti_and_ttl(
        self, client: AsyncClient
    ) -> None:
        from datetime import UTC, datetime, timedelta

        expires_at = datetime.now(UTC) + timedelta(minutes=10)

        async def _fake_current_user() -> CurrentUser:
            return CurrentUser(
                user_id=UserId.new(),
                role=Role.USER,
                token_version=0,
                jti="the-jti",
                expires_at=expires_at,
            )

        app.dependency_overrides[get_current_user] = _fake_current_user
        mock_use_case = AsyncMock(spec=LogoutUseCase)
        app.dependency_overrides[get_logout_use_case] = lambda: mock_use_case

        response = await client.post(
            "/api/v1/auth/logout", json={"refresh_token": "some-refresh-token"}
        )

        assert response.status_code == 204
        mock_use_case.execute.assert_awaited_once()
        command = mock_use_case.execute.call_args.args[0]
        assert command.raw_refresh_token == "some-refresh-token"
        assert command.access_token_jti == "the-jti"
        assert 0 < command.access_token_remaining_ttl_seconds <= 600
