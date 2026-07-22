"""E2E test for /health — per Document 6 §16.2's httpx AsyncClient pattern.

/health must never touch the DB/Redis (it's a pure liveness check), so this
test needs no testcontainers/fixtures — it exercises the real app object.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
