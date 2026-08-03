"""Unit tests for MockAiServiceClient — verifies AI_SERVICE_MODE=mock
returns well-shaped, clearly-fake responses for every method the
AiServiceClient Protocol defines, and that mutating (train/retrain/
delete) methods correctly signal "unavailable in mock mode" rather than
silently pretending to succeed.
"""

from __future__ import annotations

from src.infrastructure.http.mock_ai_service_client import MockAiServiceClient


class TestMockAiServiceClient:
    async def test_predict_echoes_the_requested_symbol(self) -> None:
        client = MockAiServiceClient()

        result = await client.predict({"symbol": "aapl"})

        assert result.status_code == 200
        assert result.body["symbol"] == "aapl"
        assert result.body["verdict"] == "hold"

    async def test_get_recommendation_uppercases_the_symbol(self) -> None:
        client = MockAiServiceClient()

        result = await client.get_recommendation("aapl")

        assert result.body["symbol"] == "AAPL"

    async def test_get_model_status_lists_all_six_required_families(self) -> None:
        client = MockAiServiceClient()

        result = await client.get_model_status()

        families = {f["family"] for f in result.body["families"]}
        assert families == {"lstm", "arima", "prophet", "random_forest", "xgboost", "finbert"}
        assert all(f["active_version"] is None for f in result.body["families"])

    async def test_train_model_returns_503_since_no_real_ai_service_is_running(self) -> None:
        client = MockAiServiceClient()

        result = await client.train_model({"family": "arima", "symbol": "AAPL"})

        assert result.status_code == 503

    async def test_retrain_model_returns_503_matching_train(self) -> None:
        client = MockAiServiceClient()

        result = await client.retrain_model({"family": "arima", "symbol": "AAPL"})

        assert result.status_code == 503

    async def test_delete_model_returns_404_since_no_registry_exists(self) -> None:
        client = MockAiServiceClient()

        result = await client.delete_model("11111111-1111-1111-1111-111111111111")

        assert result.status_code == 404

    async def test_analyze_sentiment_returns_a_neutral_placeholder(self) -> None:
        client = MockAiServiceClient()

        result = await client.analyze_sentiment({"symbol": "AAPL", "texts": ["hello"]})

        assert result.body["aggregate_label"] == "neutral"

    async def test_get_portfolio_recommendation_returns_an_empty_hold(self) -> None:
        client = MockAiServiceClient()

        result = await client.get_portfolio_recommendation(
            {"holdings": [{"symbol": "AAPL", "quantity": 1}]}
        )

        assert result.body["overall_verdict"] == "hold"

    async def test_get_metrics_reports_zero_trained_versions(self) -> None:
        client = MockAiServiceClient()

        result = await client.get_metrics()

        assert result.body["total_trained_versions"] == 0


    async def test_analyze_portfolio_intelligence_returns_a_well_formed_zeroed_result(
        self,
    ) -> None:
        client = MockAiServiceClient()

        result = await client.analyze_portfolio_intelligence(
            {
                "holdings": [
                    {"symbol": "AAPL", "quantity": 10, "market_value": 1000.0, "sector": "Tech"}
                ]
            }
        )

        assert result.status_code == 200
        assert result.body["optimization"] is None
        assert result.body["recommendations"] == []
        assert result.body["ai_predictions"]["market_exposure_pct"] == 50.0

    async def test_run_monte_carlo_simulation_echoes_the_requested_run_count(self) -> None:
        client = MockAiServiceClient()

        result = await client.run_monte_carlo_simulation(
            {
                "holdings": [
                    {"symbol": "AAPL", "quantity": 10, "market_value": 1000.0, "sector": "Tech"}
                ],
                "num_runs": 500,
                "horizon_days": 100,
            }
        )

        assert result.status_code == 200
        assert result.body["num_runs"] == 500
        assert result.body["starting_value"] == 1000.0
