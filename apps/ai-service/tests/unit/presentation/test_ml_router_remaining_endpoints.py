"""Router tests for the remaining ml_router.py endpoints: sentiment,
portfolio-recommendation, history, models/status, metrics, train, retrain.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.unit.presentation._fixtures import (
    FakeMarketDataRepository,
    FakeModelRegistryRepository,
    FakePredictionRunRepository,
    app,
    build_test_client,
    override_all_ml_dependencies,
    synthetic_bars,
)


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield build_test_client()
    app.dependency_overrides.clear()


class TestSentimentEndpoint:
    def test_analyze_sentiment_returns_aggregate_and_per_item_scores(
        self, client: TestClient
    ) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.post(
            "/api/v1/ml/sentiment",
            json={
                "symbol": "NFLX",
                "texts": [
                    "Company beats earnings expectations with record subscriber growth.",
                    "Regulatory investigation raises concerns over future profitability.",
                ],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == "NFLX"
        assert len(body["per_item_scores"]) == 2
        assert body["aggregate_label"] in {"positive", "negative", "neutral"}
        assert 0.0 <= body["aggregate_confidence"] <= 1.0
        assert body["aggregate_article_count"] == 2

    def test_analyze_sentiment_rejects_empty_texts_list(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.post("/api/v1/ml/sentiment", json={"symbol": "NFLX", "texts": []})

        assert response.status_code == 422


class TestPortfolioRecommendationEndpoint:
    def test_portfolio_recommendation_aggregates_multiple_holdings(
        self, client: TestClient
    ) -> None:
        bars_by_symbol = {
            "AAPL": synthetic_bars(n=120, seed=11),
            "MSFT": synthetic_bars(n=120, seed=22),
        }
        override_all_ml_dependencies(FakeMarketDataRepository(bars_by_symbol))

        response = client.post(
            "/api/v1/ml/portfolio-recommendation",
            json={
                "holdings": [
                    {"symbol": "AAPL", "quantity": 10},
                    {"symbol": "MSFT", "quantity": 5},
                ]
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 2
        assert body["overall_verdict"] in {"buy", "sell", "hold"}
        assert -1.0 <= body["overall_sentiment_score"] <= 1.0

    def test_portfolio_recommendation_returns_422_for_unknown_holdings(
        self, client: TestClient
    ) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.post(
            "/api/v1/ml/portfolio-recommendation",
            json={"holdings": [{"symbol": "ZZZZ", "quantity": 1}]},
        )

        assert response.status_code == 422

    def test_portfolio_recommendation_rejects_empty_holdings(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.post("/api/v1/ml/portfolio-recommendation", json={"holdings": []})

        assert response.status_code == 422


class TestPredictionHistoryEndpoint:
    def test_history_returns_previously_saved_prediction_runs(self, client: TestClient) -> None:
        bars = synthetic_bars(n=120, seed=5)
        prediction_run_repository = FakePredictionRunRepository()
        override_all_ml_dependencies(
            FakeMarketDataRepository.with_default_bars(bars),
            prediction_run_repository=prediction_run_repository,
        )

        client.post("/api/v1/ml/predict", json={"symbol": "AMZN"})
        response = client.get("/api/v1/ml/history/AMZN")

        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == "AMZN"
        assert len(body["items"]) == 1
        assert body["items"][0]["symbol"] == "AMZN"

    def test_history_returns_empty_list_for_unknown_symbol(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.get("/api/v1/ml/history/UNKNOWN")

        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_history_respects_limit_query_param(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.get("/api/v1/ml/history/AAPL?limit=5")

        assert response.status_code == 200


class TestModelStatusEndpoint:
    def test_model_status_lists_all_six_required_families(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.get("/api/v1/ml/models/status")

        assert response.status_code == 200
        families = {f["family"] for f in response.json()["families"]}
        assert families == {
            "lstm",
            "arima",
            "prophet",
            "random_forest",
            "xgboost",
            "finbert",
        }

    def test_model_status_reflects_a_registered_active_version(self, client: TestClient) -> None:
        from datetime import UTC, datetime

        from src.domain.ml.entities import ModelVersion

        registry = FakeModelRegistryRepository()
        version = ModelVersion.create(
            family="lstm",
            version_tag="v1",
            training_data_range_start=datetime(2024, 1, 1, tzinfo=UTC),
            training_data_range_end=datetime(2024, 6, 1, tzinfo=UTC),
            validation_metrics={"rmse": 1.5},
            artifact_location="/models/lstm/v1.pt",
        )
        import asyncio

        asyncio.run(registry.save(version))
        override_all_ml_dependencies(
            FakeMarketDataRepository(), model_registry_repository=registry
        )

        response = client.get("/api/v1/ml/models/status")

        assert response.status_code == 200
        lstm_status = next(
            f for f in response.json()["families"] if f["family"] == "lstm"
        )
        assert lstm_status["active_version"] is not None
        assert lstm_status["active_version"]["version_tag"] == "v1"
        assert lstm_status["version_count"] == 1


class TestDeleteModelEndpoint:
    def test_delete_removes_an_existing_model_version(self, client: TestClient) -> None:
        from datetime import UTC, datetime

        from src.domain.ml.entities import ModelVersion

        registry = FakeModelRegistryRepository()
        version = ModelVersion.create(
            family="lstm",
            version_tag="v1",
            training_data_range_start=datetime(2024, 1, 1, tzinfo=UTC),
            training_data_range_end=datetime(2024, 6, 1, tzinfo=UTC),
            validation_metrics={"rmse": 1.5},
            artifact_location="/models/lstm/v1.pt",
        )
        import asyncio

        asyncio.run(registry.save(version))
        override_all_ml_dependencies(
            FakeMarketDataRepository(), model_registry_repository=registry
        )

        response = client.delete(f"/api/v1/ml/models/{version.id}")

        assert response.status_code == 204
        status_response = client.get("/api/v1/ml/models/status")
        lstm_status = next(
            f for f in status_response.json()["families"] if f["family"] == "lstm"
        )
        assert lstm_status["version_count"] == 0

    def test_delete_returns_404_for_an_unknown_id(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.delete(
            "/api/v1/ml/models/11111111-1111-1111-1111-111111111111"
        )

        assert response.status_code == 404


class TestMetricsEndpoint:
    def test_metrics_reports_zero_versions_when_registry_empty(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.get("/api/v1/ml/metrics")

        assert response.status_code == 200
        body = response.json()
        assert len(body["model_families"]) == 6
        assert body["total_trained_versions"] == 0
        assert body["families_with_active_version"] == 0


class TestTrainAndRetrainEndpoints:
    def test_train_arima_produces_a_new_active_model_version(self, client: TestClient) -> None:
        bars = synthetic_bars(n=120, seed=9)
        override_all_ml_dependencies(FakeMarketDataRepository.with_default_bars(bars))

        response = client.post(
            "/api/v1/ml/train", json={"family": "arima", "symbol": "AAPL"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["model_version"]["status"] == "active"
        assert "rmse" in body["validation_metrics"]

    def test_train_finbert_returns_400_since_it_is_pretrained(self, client: TestClient) -> None:
        bars = synthetic_bars(n=120, seed=9)
        override_all_ml_dependencies(FakeMarketDataRepository.with_default_bars(bars))

        response = client.post(
            "/api/v1/ml/train", json={"family": "finbert", "symbol": "AAPL"}
        )

        assert response.status_code == 400

    def test_retrain_retires_the_previous_active_version(self, client: TestClient) -> None:
        bars = synthetic_bars(n=120, seed=9)
        registry = FakeModelRegistryRepository()
        override_all_ml_dependencies(
            FakeMarketDataRepository.with_default_bars(bars),
            model_registry_repository=registry,
        )

        first = client.post("/api/v1/ml/train", json={"family": "arima", "symbol": "AAPL"})
        assert first.status_code == 200

        second = client.post("/api/v1/ml/retrain", json={"family": "arima", "symbol": "AAPL"})
        assert second.status_code == 200

        status_response = client.get("/api/v1/ml/models/status")
        arima_status = next(
            f for f in status_response.json()["families"] if f["family"] == "arima"
        )
        assert arima_status["version_count"] == 2
        assert arima_status["active_version"]["id"] == second.json()["model_version"]["id"]

    def test_train_returns_422_when_no_market_data(self, client: TestClient) -> None:
        override_all_ml_dependencies(FakeMarketDataRepository())

        response = client.post(
            "/api/v1/ml/train", json={"family": "arima", "symbol": "ZZZZ"}
        )

        assert response.status_code == 422
