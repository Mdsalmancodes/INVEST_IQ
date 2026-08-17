"""
Unit tests for PortfolioIntelligenceUseCase / MonteCarloUseCase.

The PortfolioIntelligenceUseCase receives its AiPortfolioEngineService
through dependency injection.

These tests therefore use a deterministic fake AI portfolio engine.

The real production AI pipeline remains:

    ModelLoader
        ↓
    trained model artifacts
        ↓
    DecisionEngine
        ↓
    AiPortfolioEngineService

These tests are focused on orchestration and do not load real ML models.
"""

from __future__ import annotations

from src.application.portfolio_intelligence.ai_portfolio_engine_service import (
    AiPortfolioPredictions,
    SectorRiskEntry,
)
from src.application.portfolio_intelligence.data import (
    PortfolioHoldingInput,
)
from src.application.portfolio_intelligence.portfolio_intelligence_use_case import (
    MonteCarloUseCase,
    PortfolioIntelligenceUseCase,
)
from src.application.portfolio_intelligence.analytics_service import (
    PortfolioAnalytics,
)
from src.application.portfolio_intelligence.risk_metrics_service import (
    RiskMetrics,
)
from tests.unit.application.ml._fixtures import (
    FakeMarketDataRepository,
    synthetic_bars,
)


# ============================================================================
# TEST HELPERS
# ============================================================================


def _repo_for(*symbols: str) -> FakeMarketDataRepository:
    """
    Build deterministic synthetic market data for unit tests.

    This is intentionally test-only data.

    Production code continues to use the real core-api market-data
    repository.
    """

    bars_by_symbol = {
        symbol: synthetic_bars(
            120,
            seed=hash(symbol) % 1000,
        )
        for symbol in symbols
    }

    return FakeMarketDataRepository(
        bars_by_symbol=bars_by_symbol,
    )


class FakeAiPortfolioEngineService:
    """
    Test double for AiPortfolioEngineService.

    PortfolioIntelligenceUseCase only needs the service's public
    async compute() contract.

    No real ML models are loaded in these orchestration tests.
    """

    async def compute(
        self,
        data,
        analytics: PortfolioAnalytics,
        risk_metrics: RiskMetrics,
        bars_by_symbol,
    ) -> AiPortfolioPredictions:
        """
        Return a deterministic, valid AI portfolio result.

        The non-zero confidence score also proves that the
        bars_by_symbol object reached the AI layer.
        """

        assert bars_by_symbol

        return AiPortfolioPredictions(
            expected_return_pct=5.0,
            portfolio_risk_prediction=50.0,
            investment_health_prediction=75.0,
            market_exposure_pct=50.0,
            sector_risk=(
                SectorRiskEntry(
                    sector="Tech",
                    risk_score=50.0,
                ),
            ),
            portfolio_stability_score=75.0,
            portfolio_confidence_score=80.0,
        )


def _use_case(*symbols: str) -> PortfolioIntelligenceUseCase:
    """
    Construct the production use case with a test AI dependency.
    """

    return PortfolioIntelligenceUseCase(
        market_data_repository=_repo_for(*symbols),
        ai_portfolio_engine_service=FakeAiPortfolioEngineService(),
    )


# ============================================================================
# PORTFOLIO INTELLIGENCE USE CASE
# ============================================================================


class TestPortfolioIntelligenceUseCase:

    async def test_returns_a_full_result_for_a_multi_holding_portfolio(
        self,
    ) -> None:

        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=1000.0,
                sector="Tech",
            ),
            PortfolioHoldingInput(
                symbol="MSFT",
                quantity=5,
                market_value=500.0,
                sector="Tech",
            ),
        ]

        use_case = _use_case(
            "AAPL",
            "MSFT",
        )

        result = await use_case.execute(
            holdings
        )

        assert 0.0 <= result.analytics.health_score <= 100.0

        assert (
            0.0
            <= result.ai_predictions.portfolio_confidence_score
            <= 100.0
        )

        assert result.optimization is not None

        assert set(
            result.optimization.symbols
        ) == {
            "AAPL",
            "MSFT",
        }

        assert isinstance(
            result.recommendations,
            tuple,
        )

    async def test_optimization_is_none_for_a_single_holding_portfolio(
        self,
    ) -> None:

        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=1000.0,
                sector="Tech",
            )
        ]

        use_case = _use_case(
            "AAPL",
        )

        result = await use_case.execute(
            holdings
        )

        assert result.optimization is None

        assert isinstance(
            result.recommendations,
            tuple,
        )

    async def test_ai_predictions_reuse_the_same_bars_fetched_for_returns(
        self,
    ) -> None:
        """
        Regression guard for bars_out wiring.

        PortfolioIntelligenceUseCase must pass the OHLCV bars fetched
        by fetch_holdings_returns() into AiPortfolioEngineService.

        The fake AI service explicitly asserts that bars_by_symbol is
        non-empty.
        """

        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=1000.0,
                sector="Tech",
            )
        ]

        use_case = _use_case(
            "AAPL",
        )

        result = await use_case.execute(
            holdings
        )

        assert (
            result.ai_predictions.portfolio_confidence_score
            > 0.0
        )


# ============================================================================
# MONTE CARLO USE CASE
# ============================================================================


class TestMonteCarloUseCase:

    async def test_simulate_runs_end_to_end_for_a_single_holding(
        self,
    ) -> None:

        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=1000.0,
                sector="Tech",
            )
        ]

        use_case = MonteCarloUseCase(
            _repo_for("AAPL")
        )

        result = await use_case.execute(
            holdings,
            num_runs=100,
            horizon_days=30,
        )

        assert result.num_runs == 100

        assert result.horizon_days == 30

        assert result.starting_value == 1000.0

        assert (
            result.worst_case_value
            <= result.expected_case_value
            <= result.best_case_value
        )

    async def test_simulate_works_for_a_multi_holding_portfolio(
        self,
    ) -> None:

        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=1000.0,
                sector="Tech",
            ),
            PortfolioHoldingInput(
                symbol="MSFT",
                quantity=5,
                market_value=500.0,
                sector="Tech",
            ),
        ]

        use_case = MonteCarloUseCase(
            _repo_for(
                "AAPL",
                "MSFT",
            )
        )

        result = await use_case.execute(
            holdings,
            num_runs=500,
            horizon_days=252,
        )

        assert result.starting_value == 1500.0

        assert len(
            result.final_value_distribution
        ) == 500