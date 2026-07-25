"""Tests for InternalServiceAuthMiddleware — Phase 8's enforcement that
ai-service's /api/v1/ml/* surface rejects any request not carrying the
shared X-Internal-Service-Token header.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from tests.unit.presentation._fixtures import (
    FakeMarketDataRepository,
    app,
    override_all_ml_dependencies,
)


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestInternalServiceAuthMiddleware:
    def test_rejects_ml_request_with_no_token_header(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.get("/api/v1/ml/models/status")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "DIRECT_ACCESS_FORBIDDEN"

    def test_rejects_ml_request_with_wrong_token(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.get(
            "/api/v1/ml/models/status",
            headers={"X-Internal-Service-Token": "not-the-right-secret"},
        )

        assert response.status_code == 403

    def test_accepts_ml_request_with_correct_token(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())
        correct_token = get_settings().internal_service_token

        response = client.get(
            "/api/v1/ml/models/status",
            headers={"X-Internal-Service-Token": correct_token},
        )

        assert response.status_code == 200

    def test_metrics_endpoint_is_exempt_from_the_token_requirement(
        self, client: TestClient
    ) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.get("/api/v1/ml/metrics")

        assert response.status_code == 200

    def test_health_endpoint_is_unaffected(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
