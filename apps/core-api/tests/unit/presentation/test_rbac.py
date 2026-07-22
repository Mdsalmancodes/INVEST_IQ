"""Tests for RBAC dependency guards — exercised via a minimal FastAPI app
with real routes wired to require_role/require_ownership_or_role, and real
HTTP requests through httpx.AsyncClient, per Document 6 §16.2's E2E tier.
This is the correct level to test FastAPI Depends() composition at — unit-
testing the guard functions directly would not catch a wiring mistake in
how they're actually attached to a route.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.domain.auth.entities import Role
from src.domain.auth.value_objects import UserId
from src.presentation.dependencies.auth import CurrentUser, get_current_user
from src.presentation.dependencies.rbac import require_ownership_or_role, require_role

_OWNER_USER_ID = UserId.new()
_OTHER_USER_ID = UserId.new()


def _build_test_app(*, current_role: Role, current_user_id: UserId) -> FastAPI:
    app = FastAPI()

    async def _fake_current_user() -> CurrentUser:
        return CurrentUser(user_id=current_user_id, role=current_role, token_version=0)

    app.dependency_overrides[get_current_user] = _fake_current_user

    @app.get("/admin-only", dependencies=[Depends(require_role([Role.ADMIN]))])
    async def admin_only() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/owned-resource",
        dependencies=[
            Depends(
                require_ownership_or_role(
                    owner_user_id=str(_OWNER_USER_ID), allowed_roles=[Role.ADMIN]
                )
            )
        ],
    )
    async def owned_resource() -> dict[str, str]:
        return {"status": "ok"}

    return app


class TestRequireRole:
    async def test_allows_access_for_permitted_role(self) -> None:
        app = _build_test_app(current_role=Role.ADMIN, current_user_id=UserId.new())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/admin-only")
        assert response.status_code == 200

    async def test_denies_access_for_non_permitted_role(self) -> None:
        app = _build_test_app(current_role=Role.USER, current_user_id=UserId.new())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/admin-only")
        assert response.status_code == 403


class TestRequireOwnershipOrRole:
    async def test_allows_access_for_the_resource_owner(self) -> None:
        app = _build_test_app(current_role=Role.USER, current_user_id=_OWNER_USER_ID)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/owned-resource")
        assert response.status_code == 200

    async def test_allows_access_for_a_privileged_role_even_if_not_owner(self) -> None:
        app = _build_test_app(current_role=Role.ADMIN, current_user_id=_OTHER_USER_ID)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/owned-resource")
        assert response.status_code == 200

    async def test_denies_access_for_a_non_owner_non_privileged_user(self) -> None:
        app = _build_test_app(current_role=Role.USER, current_user_id=_OTHER_USER_ID)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/owned-resource")
        assert response.status_code == 403
