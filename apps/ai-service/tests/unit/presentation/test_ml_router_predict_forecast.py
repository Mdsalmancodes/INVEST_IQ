"""Router tests for POST /api/v1/ml/predict, GET /api/v1/ml/recommendation/{symbol},
and GET /api/v1/ml/forecast/{symbol} — real FastAPI TestClient, real
model training/inference, fake repository boundary only.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.unit.presentation._fixtures import (
    FakeMarketDataRepository,
    app,
    build_test_client,
    override_all_ml_dependencies,
    synthetic_bars,
)


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield build_test_client()
    app.dependency_overrides.clear()


class TestPredictEndpoint:
    def test_predict_returns_a_full_recommendation_payload(self, client: TestClient) -> None:
        bars = synthetic_bars(n=120)
        override_all_ml_dependencies(FakeMarketDataRepository.with_default_bars(bars))

        response = client.post("/api/v1/ml/predict", json={"symbol": "AAPL"})

        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == "AAPL"
        assert body["verdict"] in {"buy", "sell", "hold"}
        assert 0.0 <= body["confidence"] <= 1.0
        assert -1.0 <= body["sentiment_score"] <= 1.0
        assert body["data_quality"] in {"full", "insufficientHistory", "partialEnsemble"}
        assert len(body["contributing_models"]) >= 1
        assert "explainability" in body
        assert "top_contributions" in body["explainability"]
        assert isinstance(body["member_signals"], list)

    def test_predict_with_news_texts_includes_finbert_signal(self, client: TestClient) -> None:
        bars = synthetic_bars(n=120)
        override_all_ml_dependencies(FakeMarketDataRepository.with_default_bars(bars))

        response = client.post(
            "/api/v1/ml/predict",
            json={
                "symbol": "MSFT",
                "news_texts": ["Company reports record profits and strong growth outlook."],
            },
        )

        assert response.status_code == 200
        body = response.json()
        model_families = {s["model_family"] for s in body["member_signals"]}
        assert "finbert" in model_families

    def test_predict_returns_422_when_no_market_data_available(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())  # no bars configured

        response = client.post("/api/v1/ml/predict", json={"symbol": "ZZZZ"})

        assert response.status_code == 422

    def test_predict_rejects_empty_symbol(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.post("/api/v1/ml/predict", json={"symbol": ""})

        assert response.status_code == 422


class TestRecommendationEndpoint:
    def test_get_recommendation_matches_predict_semantics(self, client: TestClient) -> None:
        bars = synthetic_bars(n=120, seed=7)
        override_all_ml_dependencies(FakeMarketDataRepository.with_default_bars(bars))

        response = client.get("/api/v1/ml/recommendation/GOOG")

        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == "GOOG"
        assert body["verdict"] in {"buy", "sell", "hold"}


class TestForecastEndpoint:
    def test_forecast_returns_lstm_arima_prophet_member_forecasts(
        self, client: TestClient
    ) -> None:
        bars = synthetic_bars(n=120, seed=3)
        override_all_ml_dependencies(FakeMarketDataRepository.with_default_bars(bars))

        response = client.get("/api/v1/ml/forecast/TSLA")

        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == "TSLA"
        model_families = {f["model_family"] for f in body["member_forecasts"]}
        assert model_families.issubset({"lstm", "arima", "prophet"})
        assert len(body["member_forecasts"]) >= 1
        for forecast in body["member_forecasts"]:
            horizons = {p["horizon_days"] for p in forecast["points"]}
            assert horizons == {1, 7, 30}

    def test_forecast_returns_422_when_no_market_data(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.get("/api/v1/ml/forecast/ZZZZ")

        assert response.status_code == 422
