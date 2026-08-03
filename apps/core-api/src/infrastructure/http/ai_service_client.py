"""HttpAiServiceClient — implements
src.application.ai_proxy.ai_service_client.AiServiceClient for AI_SERVICE_MODE=live.

Every method calls exactly one of ai-service's existing /api/v1/ml/*
endpoints (built Phase 7), always attaching the shared
X-Internal-Service-Token header ai-service's own
InternalServiceAuthMiddleware requires (apps/ai-service/src/presentation/
internal_auth_middleware.py) — this is the one and only place in the
entire monorepo that sends that header, since core-api's AiServiceClient
is the one and only permitted caller of ai-service (Document 3 §7.1,
enforced at the code level this phase, not just by docker-compose network
topology — see docs/phase-8/known-issues.md for the full rationale).

Deliberately forwards ai-service's response body and status code
unmodified on both success and error (never re-wraps or reinterprets
ai-service's own error shape) — the proxy's job is authorization +
routing, not response transformation.
"""

from __future__ import annotations

from typing import Any

import httpx

from src.application.ai_proxy.ai_service_client import AiServiceResponse


class HttpAiServiceClient:
    def __init__(
        self,
        base_url: str,
        internal_service_token: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_service_token = internal_service_token
        self._timeout_seconds = timeout_seconds
        self._injected_client = client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> AiServiceResponse:
        headers = {"X-Internal-Service-Token": self._internal_service_token}
        if self._injected_client is not None:
            response = await self._injected_client.request(
                method, f"{self._base_url}{path}", json=json_body, params=params, headers=headers
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json_body,
                    params=params,
                    headers=headers,
                )
        return AiServiceResponse(
            status_code=response.status_code,
            body=response.json() if response.content else {},
        )

    async def predict(self, payload: dict[str, Any]) -> AiServiceResponse:
        return await self._request("POST", "/api/v1/ml/predict", json_body=payload)

    async def get_recommendation(self, symbol: str) -> AiServiceResponse:
        return await self._request("GET", f"/api/v1/ml/recommendation/{symbol}")

    async def get_forecast(self, symbol: str, lookback_days: int | None) -> AiServiceResponse:
        params = {"lookback_days": lookback_days} if lookback_days is not None else None
        return await self._request("GET", f"/api/v1/ml/forecast/{symbol}", params=params)

    async def analyze_sentiment(self, payload: dict[str, Any]) -> AiServiceResponse:
        return await self._request("POST", "/api/v1/ml/sentiment", json_body=payload)

    async def get_portfolio_recommendation(self, payload: dict[str, Any]) -> AiServiceResponse:
        return await self._request(
            "POST", "/api/v1/ml/portfolio-recommendation", json_body=payload
        )

    async def get_prediction_history(self, symbol: str, limit: int | None) -> AiServiceResponse:
        params = {"limit": limit} if limit is not None else None
        return await self._request("GET", f"/api/v1/ml/history/{symbol}", params=params)

    async def get_model_status(self) -> AiServiceResponse:
        return await self._request("GET", "/api/v1/ml/models/status")

    async def get_metrics(self) -> AiServiceResponse:
        return await self._request("GET", "/api/v1/ml/metrics")

    async def train_model(self, payload: dict[str, Any]) -> AiServiceResponse:
        return await self._request("POST", "/api/v1/ml/train", json_body=payload)

    async def retrain_model(self, payload: dict[str, Any]) -> AiServiceResponse:
        return await self._request("POST", "/api/v1/ml/retrain", json_body=payload)

    async def delete_model(self, model_version_id: str) -> AiServiceResponse:
        return await self._request("DELETE", f"/api/v1/ml/models/{model_version_id}")

    # --- Phase 10 (AI Portfolio Intelligence) ---

    async def analyze_portfolio_intelligence(self, payload: dict[str, Any]) -> AiServiceResponse:
        return await self._request(
            "POST", "/api/v1/portfolio-intelligence/analyze", json_body=payload
        )

    async def run_monte_carlo_simulation(self, payload: dict[str, Any]) -> AiServiceResponse:
        return await self._request(
            "POST", "/api/v1/portfolio-intelligence/monte-carlo", json_body=payload
        )
