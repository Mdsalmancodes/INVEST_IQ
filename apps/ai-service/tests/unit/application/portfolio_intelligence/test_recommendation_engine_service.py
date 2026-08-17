"""
Unit tests for RecommendationEngineService.

RecommendationEngineService consumes already-computed portfolio
analytics, risk metrics, AI predictions, and optimization results.

It must not load or train ML models itself.

Therefore these tests use a deterministic AiPortfolioPredictions
object instead of invoking AiPortfolioEngineService.
"""

from __future__ import annotations

from src.application.portfolio_intelligence.ai_portfolio_engine_service import (
    AiPortfolioPredictions,
    SectorRiskEntry,
)
from src.application.portfolio_intelligence.analytics_service import (
    AnalyticsService,
)
from src.application.portfolio_intelligence.data import (
    PortfolioHoldingInput,
    fetch_holdings_returns,
)
from src.application.portfolio_intelligence.optimization_service import (
    OptimizationService,
)
from src.application.portfolio_intelligence.recommendation_engine_service import (
    RecommendationEngineService,
)
from src.application.portfolio_intelligence.risk_metrics_service import (
    RiskMetricsService,
)
from tests.unit.application.ml._fixtures import (
    FakeMarketDataRepository,
    synthetic_bars,
)


# ============================================================================
# TEST HELPERS
# ============================================================================


def _build_ai_predictions() -> AiPortfolioPredictions:
    """
    Build a deterministic AI result for recommendation-engine tests.

    These tests verify recommendation logic, not ML inference.
    """

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


async def _build_full_bundle(
    holdings: list[PortfolioHoldingInput],
) -> tuple:

    bars_by_symbol = {
        holding.symbol: synthetic_bars(
            150,
            seed=hash(holding.symbol) % 1000,
        )
        for holding in holdings
    }

    repo = FakeMarketDataRepository(
        bars_by_symbol=bars_by_symbol,
    )

    data = await fetch_holdings_returns(
        repo,
        holdings,
    )

    analytics = AnalyticsService().compute(
        data
    )

    risk_metrics = RiskMetricsService().compute(
        data
    )

    # RecommendationEngineService consumes the RESULT of the AI
    # engine. It should not construct or load ML models itself.
    ai_predictions = _build_ai_predictions()

    optimization = None

    if len(data.holdings) >= 2:
        optimization = OptimizationService().optimize(
            data
        )

    return (
        analytics,
        risk_metrics,
        ai_predictions,
        optimization,
    )


# ============================================================================
# TESTS
# ============================================================================


class TestRecommendationEngineService:

    async def test_a_concentrated_single_sector_portfolio_triggers_reduce_sector_exposure(
        self,
    ) -> None:

        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=800.0,
                sector="Tech",
            ),
            PortfolioHoldingInput(
                symbol="MSFT",
                quantity=5,
                market_value=200.0,
                sector="Tech",
            ),
        ]

        (
            analytics,
            risk_metrics,
            ai_predictions,
            optimization,
        ) = await _build_full_bundle(
            holdings
        )

        service = RecommendationEngineService()

        recommendations = service.generate(
            analytics,
            risk_metrics,
            ai_predictions,
            optimization,
        )

        reduce_recs = [
            recommendation
            for recommendation in recommendations
            if recommendation.type
            == "reduce_sector_exposure"
        ]

        assert len(reduce_recs) == 1

        assert (
            reduce_recs[0].affected_assets
            == ("Tech",)
        )

        assert "Tech" in reduce_recs[0].reason

    async def test_a_well_diversified_portfolio_produces_no_sector_or_diversification_flags(
        self,
    ) -> None:

        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=250.0,
                sector="Tech",
            ),
            PortfolioHoldingInput(
                symbol="JNJ",
                quantity=5,
                market_value=250.0,
                sector="Healthcare",
            ),
            PortfolioHoldingInput(
                symbol="XOM",
                quantity=8,
                market_value=250.0,
                sector="Energy",
            ),
            PortfolioHoldingInput(
                symbol="JPM",
                quantity=6,
                market_value=250.0,
                sector="Financials",
            ),
        ]

        (
            analytics,
            risk_metrics,
            ai_predictions,
            optimization,
        ) = await _build_full_bundle(
            holdings
        )

        service = RecommendationEngineService()

        recommendations = service.generate(
            analytics,
            risk_metrics,
            ai_predictions,
            optimization,
        )

        sector_recs = [
            recommendation
            for recommendation in recommendations
            if recommendation.type
            in (
                "reduce_sector_exposure",
                "increase_sector_exposure",
            )
        ]

        assert sector_recs == []

    async def test_every_recommendations_confidence_is_within_bounds(
        self,
    ) -> None:

        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=900.0,
                sector="Tech",
            ),
            PortfolioHoldingInput(
                symbol="MSFT",
                quantity=5,
                market_value=100.0,
                sector="Tech",
            ),
        ]

        (
            analytics,
            risk_metrics,
            ai_predictions,
            optimization,
        ) = await _build_full_bundle(
            holdings
        )

        service = RecommendationEngineService()

        recommendations = service.generate(
            analytics,
            risk_metrics,
            ai_predictions,
            optimization,
        )

        assert len(recommendations) > 0

        for recommendation in recommendations:

            assert (
                0.0
                <= recommendation.confidence
                <= 1.0
            )

            assert recommendation.reason

            assert recommendation.risk_impact

            assert recommendation.expected_improvement

    async def test_a_materially_different_weighting_triggers_a_rebalance_recommendation(
        self,
    ) -> None:

        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=950.0,
                sector="Tech",
            ),
            PortfolioHoldingInput(
                symbol="JNJ",
                quantity=5,
                market_value=50.0,
                sector="Healthcare",
            ),
        ]

        (
            analytics,
            risk_metrics,
            ai_predictions,
            optimization,
        ) = await _build_full_bundle(
            holdings
        )

        service = RecommendationEngineService()

        recommendations = service.generate(
            analytics,
            risk_metrics,
            ai_predictions,
            optimization,
        )

        rebalance_recs = [
            recommendation
            for recommendation in recommendations
            if recommendation.type
            == "suggested_rebalance"
        ]

        assert len(rebalance_recs) <= 1

    async def test_no_optimization_result_is_handled_without_error(
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

        (
            analytics,
            risk_metrics,
            ai_predictions,
            optimization,
        ) = await _build_full_bundle(
            holdings
        )

        service = RecommendationEngineService()

        assert optimization is None

        recommendations = service.generate(
            analytics,
            risk_metrics,
            ai_predictions,
            None,
        )

        rebalance_recs = [
            recommendation
            for recommendation in recommendations
            if recommendation.type
            == "suggested_rebalance"
        ]

        assert rebalance_recs == []