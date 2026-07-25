"""Tests for SecurityHeadersMiddleware — verifies every response carries
the §15.5-specified header set, using the real app (headers should apply
to every route uniformly, so testing against a real endpoint like /health
is representative of the whole app, not just a synthetic test route)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSecurityHeadersMiddleware:
    async def test_response_carries_all_expected_security_headers(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/health")

        assert response.headers["Strict-Transport-Security"] == (
            "max-age=63072000; includeSubDomains; preload"
        )
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["Permissions-Policy"] == (
            "geolocation=(), microphone=(), camera=()"
        )

    async def test_headers_are_present_even_on_an_error_response(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/ai/models/status")  # unauthenticated -> 401

        assert response.status_code == 401
        assert "X-Content-Type-Options" in response.headers
