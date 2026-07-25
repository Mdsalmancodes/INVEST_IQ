"""MockAiServiceClient — implements
src.application.ai_proxy.ai_service_client.AiServiceClient for
AI_SERVICE_MODE=mock (Document 3 §7.1's documented pattern, finally
implemented this phase — previously only referenced by config.py's
comments and infra/docker-compose.yml, with no actual class anywhere in
the codebase until now).

Used when core-api runs without the "ml" docker-compose profile — lets
every other part of the platform (auth, RBAC, rate limiting, the proxy
router's own request validation) be developed and tested without a real
ai-service instance running, returning small, clearly-fake-shaped
responses rather than failing every AI-proxy request outright.
"""

from __future__ import annotations

from typing import Any

from src.application.ai_proxy.ai_service_client import AiServiceResponse

_MOCK_RECOMMENDATION: dict[str, Any] = {
    "symbol": "MOCK",
    "verdict": "hold",
    "confidence": 0.5,
    "price_forecast": 100.0,
    "sentiment_score": 0.0,
    "data_quality": "insufficientHistory",
    "contributing_models": [],
    "explainability": {
        "top_contributions": [],
        "base_value": 0.0,
        "method": "mock",
        "reasoning": "AI_SERVICE_MODE=mock — no real ai-service instance is running.",
    },
    "member_signals": [],
    "excluded_models": [
        "lstm",
        "arima",
        "prophet",
        "random_forest",
        "xgboost",
        "finbert",
    ],
    "price_forecast_7d": 100.0,
    "price_forecast_30d": 100.0,
}

_MOCK_MODEL_STATUS: dict[str, Any] = {
    "families": [
        {"family": family, "active_version": None, "version_count": 0}
        for family in ("lstm", "arima", "prophet", "random_forest", "xgboost", "finbert")
    ]
}


class MockAiServiceClient:
    async def predict(self, payload: dict[str, Any]) -> AiServiceResponse:
        symbol = payload.get("symbol", "MOCK")
        return AiServiceResponse(status_code=200, body={**_MOCK_RECOMMENDATION, "symbol": symbol})

    async def get_recommendation(self, symbol: str) -> AiServiceResponse:
        return AiServiceResponse(
            status_code=200, body={**_MOCK_RECOMMENDATION, "symbol": symbol.upper()}
        )

    async def get_forecast(self, symbol: str, lookback_days: int | None) -> AiServiceResponse:
        return AiServiceResponse(
            status_code=200,
            body={"symbol": symbol.upper(), "member_forecasts": [], "excluded_models": []},
        )

    async def analyze_sentiment(self, payload: dict[str, Any]) -> AiServiceResponse:
        return AiServiceResponse(
            status_code=200,
            body={
                "symbol": payload.get("symbol", "MOCK"),
                "per_item_scores": [],
                "aggregate_label": "neutral",
                "aggregate_confidence": 0.0,
                "aggregate_article_count": 0,
            },
        )

    async def get_portfolio_recommendation(self, payload: dict[str, Any]) -> AiServiceResponse:
        return AiServiceResponse(
            status_code=200,
            body={"items": [], "overall_verdict": "hold", "overall_sentiment_score": 0.0},
        )

    async def get_prediction_history(self, symbol: str, limit: int | None) -> AiServiceResponse:
        return AiServiceResponse(status_code=200, body={"symbol": symbol.upper(), "items": []})

    async def get_model_status(self) -> AiServiceResponse:
        return AiServiceResponse(status_code=200, body=_MOCK_MODEL_STATUS)

    async def get_metrics(self) -> AiServiceResponse:
        return AiServiceResponse(
            status_code=200,
            body={
                "model_families": [
                    {"family": f, "has_active_version": False, "trained_version_count": 0}
                    for f in ("lstm", "arima", "prophet", "random_forest", "xgboost", "finbert")
                ],
                "total_trained_versions": 0,
                "families_with_active_version": 0,
            },
        )

    async def train_model(self, payload: dict[str, Any]) -> AiServiceResponse:
        return AiServiceResponse(
            status_code=503,
            body={
                "detail": (
                    "AI_SERVICE_MODE=mock — training requires a real ai-service "
                    "instance (start the 'ml' docker-compose profile)."
                )
            },
        )

    async def retrain_model(self, payload: dict[str, Any]) -> AiServiceResponse:
        return await self.train_model(payload)

    async def delete_model(self, model_version_id: str) -> AiServiceResponse:
        return AiServiceResponse(
            status_code=404,
            body={"detail": "AI_SERVICE_MODE=mock — no model registry is available."},
        )
