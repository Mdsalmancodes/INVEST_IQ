"""Router tests for POST /api/v1/portfolio-intelligence/analyze and
POST /api/v1/portfolio-intelligence/monte-carlo — real FastAPI
TestClient, real quantitative computation (numpy/scipy), fake repository
boundary only, same pattern as test_ml_router_predict_forecast.py.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.application.portfolio_intelligence.monte_carlo_service import MonteCarloService
from src.application.portfolio_intelligence.portfolio_intelligence_use_case import (
    MonteCarloUseCase,
    PortfolioIntelligenceUseCase,
)
from src.presentation.dependencies.portfolio_intelligence_use_cases import (
    get_monte_carlo_use_case,
    get_portfolio_intelligence_use_case,
)
from tests.unit.presentation._fixtures import (
    FakeMarketDataRepository,
    app,
    build_test_client,
    synthetic_bars,
)


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield build_test_client()
    app.dependency_overrides.clear()


def _override_with(repo: FakeMarketDataRepository) -> None:
    app.dependency_overrides[get_portfolio_intelligence_use_case] = (
        lambda: PortfolioIntelligenceUseCase(repo)
    )
    app.dependency_overrides[get_monte_carlo_use_case] = lambda: MonteCarloUseCase(
        repo, MonteCarloService()
    )


class TestAnalyzeEndpoint:
    def test_analyze_returns_a_full_intelligence_payload_for_two_holdings(
        self, client: TestClient
    ) -> None:
        repo = FakeMarketDataRepository(
            bars_by_symbol={
                "AAPL": synthetic_bars(120, seed=1),
                "MSFT": synthetic_bars(120, seed=2),
            }
        )
        _override_with(repo)

        response = client.post(
            "/api/v1/portfolio-intelligence/analyze",
            json={
                "holdings": [
                    {
                        "symbol": "AAPL",
                        "quantity": 10,
                        "market_value": 1000.0,
                        "sector": "Tech",
                    },
                    {
                        "symbol": "MSFT",
                        "quantity": 5,
                        "market_value": 500.0,
                        "sector": "Tech",
                    },
                ],
                "lookback_days": 400,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert 0.0 <= body["analytics"]["health_score"] <= 100.0
        assert 0.0 <= body["ai_predictions"]["portfolio_confidence_score"] <= 100.0
        assert body["optimization"] is not None
        assert set(body["optimization"]["symbols"]) == {"AAPL", "MSFT"}
        assert isinstance(body["recommendations"], list)

    def test_analyze_returns_null_optimization_for_a_single_holding(
        self, client: TestClient
    ) -> None:
        repo = FakeMarketDataRepository(bars_by_symbol={"AAPL": synthetic_bars(120, seed=1)})
        _override_with(repo)

        response = client.post(
            "/api/v1/portfolio-intelligence/analyze",
            json={
                "holdings": [
                    {"symbol": "AAPL", "quantity": 10, "market_value": 1000.0, "sector": "Tech"}
                ]
            },
        )

        assert response.status_code == 200
        assert response.json()["optimization"] is None

    def test_analyze_rejects_an_empty_holdings_list(self, client: TestClient) -> None:
        repo = FakeMarketDataRepository()
        _override_with(repo)

        response = client.post(
            "/api/v1/portfolio-intelligence/analyze", json={"holdings": []}
        )

        assert response.status_code == 422


class TestMonteCarloEndpoint:
    def test_monte_carlo_returns_a_valid_simulation_result(self, client: TestClient) -> None:
        repo = FakeMarketDataRepository(bars_by_symbol={"AAPL": synthetic_bars(120, seed=1)})
        _override_with(repo)

        response = client.post(
            "/api/v1/portfolio-intelligence/monte-carlo",
            json={
                "holdings": [
                    {"symbol": "AAPL", "quantity": 10, "market_value": 1000.0, "sector": "Tech"}
                ],
                "num_runs": 100,
                "horizon_days": 30,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["num_runs"] == 100
        assert body["starting_value"] == 1000.0
        assert body["worst_case_value"] <= body["expected_case_value"] <= body["best_case_value"]

    def test_monte_carlo_rejects_an_invalid_run_count(self, client: TestClient) -> None:
        repo = FakeMarketDataRepository(bars_by_symbol={"AAPL": synthetic_bars(120, seed=1)})
        _override_with(repo)

        response = client.post(
            "/api/v1/portfolio-intelligence/monte-carlo",
            json={
                "holdings": [
                    {"symbol": "AAPL", "quantity": 10, "market_value": 1000.0, "sector": "Tech"}
                ],
                "num_runs": 999,
                "horizon_days": 30,
            },
        )

        assert response.status_code == 400
