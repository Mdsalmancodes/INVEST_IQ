"""Tests for ai_proxy_router.py — the sole path core-api exposes to reach
ai-service's capabilities (Phase 8). Exercised the same way test_rbac.py
does: the real `app`, real HTTP requests via httpx.ASGITransport, with
get_current_user and get_ai_service_client overridden via FastAPI's
dependency_overrides (get_audit_logger is also overridden for the 3
admin-only mutating endpoints, since those write a real Postgres row via
SqlAlchemyAuditLogRepository otherwise, which this unit-test tier does not
have a database connection for).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.application.ai_proxy.ai_service_client import AiServiceResponse
from src.application.auth.audit_logger import AuditLogger
from src.domain.auth.entities import Role
from src.domain.auth.value_objects import UserId
from src.main import app
from src.presentation.dependencies.ai_proxy_use_cases import get_ai_service_client, get_audit_logger
from src.presentation.dependencies.auth import CurrentUser, get_current_user


class FakeAiServiceClient:
    """Records every call made to it and returns a pre-configured
    AiServiceResponse — lets each test assert the proxy forwarded the
    right method/args and mirrored the response back unmodified, without
    a real ai-service instance or HTTP call."""

    def __init__(self, response: AiServiceResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def predict(self, payload: dict[str, Any]) -> AiServiceResponse:
        self.calls.append(("predict", (payload,)))
        return self.response

    async def get_recommendation(self, symbol: str) -> AiServiceResponse:
        self.calls.append(("get_recommendation", (symbol,)))
        return self.response

    async def get_forecast(self, symbol: str, lookback_days: int | None) -> AiServiceResponse:
        self.calls.append(("get_forecast", (symbol, lookback_days)))
        return self.response

    async def analyze_sentiment(self, payload: dict[str, Any]) -> AiServiceResponse:
        self.calls.append(("analyze_sentiment", (payload,)))
        return self.response

    async def get_portfolio_recommendation(self, payload: dict[str, Any]) -> AiServiceResponse:
        self.calls.append(("get_portfolio_recommendation", (payload,)))
        return self.response

    async def get_prediction_history(self, symbol: str, limit: int | None) -> AiServiceResponse:
        self.calls.append(("get_prediction_history", (symbol, limit)))
        return self.response

    async def get_model_status(self) -> AiServiceResponse:
        self.calls.append(("get_model_status", ()))
        return self.response

    async def get_metrics(self) -> AiServiceResponse:
        self.calls.append(("get_metrics", ()))
        return self.response

    async def train_model(self, payload: dict[str, Any]) -> AiServiceResponse:
        self.calls.append(("train_model", (payload,)))
        return self.response

    async def retrain_model(self, payload: dict[str, Any]) -> AiServiceResponse:
        self.calls.append(("retrain_model", (payload,)))
        return self.response

    async def delete_model(self, model_version_id: str) -> AiServiceResponse:
        self.calls.append(("delete_model", (model_version_id,)))
        return self.response


def _set_current_user(role: Role) -> None:
    async def _fake_current_user() -> CurrentUser:
        return CurrentUser(user_id=UserId.new(), role=role, token_version=0)

    app.dependency_overrides[get_current_user] = _fake_current_user


def _set_ai_client(fake_client: FakeAiServiceClient) -> None:
    app.dependency_overrides[get_ai_service_client] = lambda: fake_client


def _set_fake_audit_logger() -> AsyncMock:
    mock_logger = AsyncMock(spec=AuditLogger)
    app.dependency_overrides[get_audit_logger] = lambda: mock_logger
    return mock_logger


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestNonAdminEndpointsRequireAuthOnly:
    async def test_predict_forwards_to_ai_service_client_for_a_basic_user(
        self, client: AsyncClient
    ) -> None:
        fake_client = FakeAiServiceClient(AiServiceResponse(status_code=200, body={"ok": True}))
        _set_current_user(Role.USER)
        _set_ai_client(fake_client)

        response = await client.post("/api/v1/ai/predict", json={"symbol": "AAPL"})

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert fake_client.calls[0][0] == "predict"

    async def test_predict_rejects_an_unauthenticated_caller(self, client: AsyncClient) -> None:
        # No override for get_current_user — the real dependency runs and
        # requires a bearer token, which this request doesn't provide.
        app.dependency_overrides.pop(get_current_user, None)
        _set_ai_client(FakeAiServiceClient(AiServiceResponse(status_code=200, body={})))

        response = await client.post("/api/v1/ai/predict", json={"symbol": "AAPL"})

        assert response.status_code == 401

    async def test_get_recommendation_mirrors_ai_service_status_code_on_error(
        self, client: AsyncClient
    ) -> None:
        fake_client = FakeAiServiceClient(
            AiServiceResponse(status_code=422, body={"detail": "insufficient history"})
        )
        _set_current_user(Role.PRO_USER)
        _set_ai_client(fake_client)

        response = await client.get("/api/v1/ai/recommendation/ZZZZ")

        assert response.status_code == 422
        assert response.json() == {"detail": "insufficient history"}

    async def test_forecast_forwards_lookback_days_query_param(self, client: AsyncClient) -> None:
        fake_client = FakeAiServiceClient(AiServiceResponse(status_code=200, body={}))
        _set_current_user(Role.USER)
        _set_ai_client(fake_client)

        await client.get("/api/v1/ai/forecast/AAPL?lookback_days=500")

        assert fake_client.calls[0] == ("get_forecast", ("AAPL", 500))

    async def test_sentiment_available_to_any_authenticated_role(
        self, client: AsyncClient
    ) -> None:
        fake_client = FakeAiServiceClient(AiServiceResponse(status_code=200, body={}))
        _set_current_user(Role.USER)
        _set_ai_client(fake_client)

        response = await client.post(
            "/api/v1/ai/sentiment", json={"symbol": "AAPL", "texts": ["Great earnings."]}
        )

        assert response.status_code == 200

    async def test_portfolio_recommendation_available_to_any_authenticated_role(
        self, client: AsyncClient
    ) -> None:
        fake_client = FakeAiServiceClient(AiServiceResponse(status_code=200, body={}))
        _set_current_user(Role.PRO_USER)
        _set_ai_client(fake_client)

        response = await client.post(
            "/api/v1/ai/portfolio-recommendation",
            json={"holdings": [{"symbol": "AAPL", "quantity": 1}]},
        )

        assert response.status_code == 200

    async def test_prediction_history_available_to_any_authenticated_role(
        self, client: AsyncClient
    ) -> None:
        fake_client = FakeAiServiceClient(AiServiceResponse(status_code=200, body={}))
        _set_current_user(Role.USER)
        _set_ai_client(fake_client)

        response = await client.get("/api/v1/ai/history/AAPL")

        assert response.status_code == 200


class TestAdminOnlyEndpoints:
    async def test_model_status_is_forbidden_for_a_basic_user(self, client: AsyncClient) -> None:
        _set_current_user(Role.USER)
        _set_ai_client(FakeAiServiceClient(AiServiceResponse(status_code=200, body={})))

        response = await client.get("/api/v1/ai/models/status")

        assert response.status_code == 403

    async def test_model_status_is_forbidden_for_a_premium_user(
        self, client: AsyncClient
    ) -> None:
        _set_current_user(Role.PRO_USER)
        _set_ai_client(FakeAiServiceClient(AiServiceResponse(status_code=200, body={})))

        response = await client.get("/api/v1/ai/models/status")

        assert response.status_code == 403

    async def test_model_status_is_allowed_for_an_admin(self, client: AsyncClient) -> None:
        fake_client = FakeAiServiceClient(AiServiceResponse(status_code=200, body={"families": []}))
        _set_current_user(Role.ADMIN)
        _set_ai_client(fake_client)

        response = await client.get("/api/v1/ai/models/status")

        assert response.status_code == 200
        assert fake_client.calls[0][0] == "get_model_status"

    async def test_model_status_is_allowed_for_a_super_admin(self, client: AsyncClient) -> None:
        _set_current_user(Role.SUPER_ADMIN)
        _set_ai_client(FakeAiServiceClient(AiServiceResponse(status_code=200, body={})))

        response = await client.get("/api/v1/ai/models/status")

        assert response.status_code == 200

    async def test_train_model_is_forbidden_for_a_basic_user(self, client: AsyncClient) -> None:
        _set_current_user(Role.USER)
        _set_ai_client(FakeAiServiceClient(AiServiceResponse(status_code=200, body={})))
        _set_fake_audit_logger()

        response = await client.post(
            "/api/v1/ai/models/train", json={"family": "arima", "symbol": "AAPL"}
        )

        assert response.status_code == 403

    async def test_train_model_is_allowed_for_an_admin_and_writes_an_audit_log(
        self, client: AsyncClient
    ) -> None:
        fake_client = FakeAiServiceClient(
            AiServiceResponse(status_code=200, body={"model_version": {}})
        )
        _set_current_user(Role.ADMIN)
        _set_ai_client(fake_client)
        mock_logger = _set_fake_audit_logger()

        response = await client.post(
            "/api/v1/ai/models/train", json={"family": "arima", "symbol": "AAPL"}
        )

        assert response.status_code == 200
        assert fake_client.calls[0] == (
            "train_model",
            ({"family": "arima", "symbol": "AAPL", "lookback_days": 400},),
        )
        mock_logger.record.assert_awaited_once()
        assert mock_logger.record.call_args.kwargs["action"] == "ai.model.train"

    async def test_retrain_model_is_forbidden_for_a_premium_user(
        self, client: AsyncClient
    ) -> None:
        _set_current_user(Role.PRO_USER)
        _set_ai_client(FakeAiServiceClient(AiServiceResponse(status_code=200, body={})))
        _set_fake_audit_logger()

        response = await client.post(
            "/api/v1/ai/models/retrain", json={"family": "arima", "symbol": "AAPL"}
        )

        assert response.status_code == 403

    async def test_retrain_model_is_allowed_for_an_admin(self, client: AsyncClient) -> None:
        fake_client = FakeAiServiceClient(AiServiceResponse(status_code=200, body={}))
        _set_current_user(Role.ADMIN)
        _set_ai_client(fake_client)
        mock_logger = _set_fake_audit_logger()

        response = await client.post(
            "/api/v1/ai/models/retrain", json={"family": "lstm", "symbol": "AAPL"}
        )

        assert response.status_code == 200
        assert fake_client.calls[0][0] == "retrain_model"
        mock_logger.record.assert_awaited_once()

    async def test_delete_model_is_forbidden_for_a_basic_user(self, client: AsyncClient) -> None:
        _set_current_user(Role.USER)
        _set_ai_client(FakeAiServiceClient(AiServiceResponse(status_code=204, body={})))
        _set_fake_audit_logger()

        response = await client.delete(
            "/api/v1/ai/models/11111111-1111-1111-1111-111111111111"
        )

        assert response.status_code == 403

    async def test_delete_model_is_allowed_for_an_admin_and_writes_an_audit_log(
        self, client: AsyncClient
    ) -> None:
        fake_client = FakeAiServiceClient(AiServiceResponse(status_code=204, body={}))
        _set_current_user(Role.ADMIN)
        _set_ai_client(fake_client)
        mock_logger = _set_fake_audit_logger()

        response = await client.delete(
            "/api/v1/ai/models/11111111-1111-1111-1111-111111111111"
        )

        assert response.status_code == 204
        assert fake_client.calls[0] == (
            "delete_model",
            ("11111111-1111-1111-1111-111111111111",),
        )
        mock_logger.record.assert_awaited_once()
        assert mock_logger.record.call_args.kwargs["action"] == "ai.model.delete"
