"""Unit tests for PortfolioIntelligenceUseCase / MonteCarloUseCase — the
orchestrating integration layer added to close the ML verification
audit's "no API route" gap for Monte Carlo simulation and Portfolio
Optimization. These tests confirm the orchestrator correctly wires
together AnalyticsService, RiskMetricsService, AiPortfolioEngineService,
OptimizationService, and RecommendationEngineService (each already
covered by its own dedicated test file) — not re-testing their internal
math.
"""

from __future__ import annotations

from src.application.portfolio_intelligence.data import PortfolioHoldingInput
from src.application.portfolio_intelligence.portfolio_intelligence_use_case import (
    MonteCarloUseCase,
    PortfolioIntelligenceUseCase,
)
from tests.unit.application.ml._fixtures import FakeMarketDataRepository, synthetic_bars


def _repo_for(*symbols: str) -> FakeMarketDataRepository:
    bars_by_symbol = {s: synthetic_bars(120, seed=hash(s) % 1000) for s in symbols}
    return FakeMarketDataRepository(bars_by_symbol=bars_by_symbol)


class TestPortfolioIntelligenceUseCase:
    async def test_returns_a_full_result_for_a_multi_holding_portfolio(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech"),
            PortfolioHoldingInput(symbol="MSFT", quantity=5, market_value=500.0, sector="Tech"),
        ]
        use_case = PortfolioIntelligenceUseCase(_repo_for("AAPL", "MSFT"))

        result = await use_case.execute(holdings)

        assert 0.0 <= result.analytics.health_score <= 100.0
        assert 0.0 <= result.ai_predictions.portfolio_confidence_score <= 100.0
        assert result.optimization is not None
        assert set(result.optimization.symbols) == {"AAPL", "MSFT"}
        assert isinstance(result.recommendations, tuple)

    async def test_optimization_is_none_for_a_single_holding_portfolio(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        use_case = PortfolioIntelligenceUseCase(_repo_for("AAPL"))

        result = await use_case.execute(holdings)

        # OptimizationService.optimize() raises for <2 holdings — the use
        # case must catch that and surface None, not propagate the error,
        # per RecommendationEngineService.generate()'s own existing
        # "optimization is optional" contract.
        assert result.optimization is None
        assert isinstance(result.recommendations, tuple)

    async def test_ai_predictions_reuse_the_same_bars_fetched_for_returns(self) -> None:
        """Regression guard for the bars_out wiring: AiPortfolioEngineService
        must receive non-empty bars_by_symbol (proving fetch_holdings_returns'
        new bars_out parameter is actually populated and passed through),
        not the empty-dict fallback that produces an all-zero result."""
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        use_case = PortfolioIntelligenceUseCase(_repo_for("AAPL"))

        result = await use_case.execute(holdings)

        # If bars_by_symbol had been empty, portfolio_confidence_score
        # would be exactly 0.0 (per AiPortfolioEngineService's own
        # documented "missing bars -> zeroed result" behavior).
        assert result.ai_predictions.portfolio_confidence_score > 0.0


class TestMonteCarloUseCase:
    async def test_simulate_runs_end_to_end_for_a_single_holding(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        use_case = MonteCarloUseCase(_repo_for("AAPL"))

        result = await use_case.execute(holdings, num_runs=100, horizon_days=30)

        assert result.num_runs == 100
        assert result.horizon_days == 30
        assert result.starting_value == 1000.0
        assert result.worst_case_value <= result.expected_case_value <= result.best_case_value

    async def test_simulate_works_for_a_multi_holding_portfolio(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech"),
            PortfolioHoldingInput(symbol="MSFT", quantity=5, market_value=500.0, sector="Tech"),
        ]
        use_case = MonteCarloUseCase(_repo_for("AAPL", "MSFT"))

        result = await use_case.execute(holdings, num_runs=500, horizon_days=252)

        assert result.starting_value == 1500.0
        assert len(result.final_value_distribution) == 500
