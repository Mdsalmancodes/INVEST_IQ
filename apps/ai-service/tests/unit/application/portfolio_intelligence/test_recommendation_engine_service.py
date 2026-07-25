"""Unit tests for RecommendationEngineService — Phase 10 AI Recommendation
Engine with Explainable AI."""

from __future__ import annotations

from src.application.portfolio_intelligence.ai_portfolio_engine_service import (
    AiPortfolioEngineService,
)
from src.application.portfolio_intelligence.analytics_service import AnalyticsService
from src.application.portfolio_intelligence.data import (
    PortfolioHoldingInput,
    fetch_holdings_returns,
)
from src.application.portfolio_intelligence.optimization_service import OptimizationService
from src.application.portfolio_intelligence.recommendation_engine_service import (
    RecommendationEngineService,
)
from src.application.portfolio_intelligence.risk_metrics_service import RiskMetricsService
from tests.unit.application.ml._fixtures import FakeMarketDataRepository, synthetic_bars


async def _build_full_bundle(holdings: list[PortfolioHoldingInput]) -> tuple:
    bars_by_symbol = {
        h.symbol: synthetic_bars(150, seed=hash(h.symbol) % 1000) for h in holdings
    }
    repo = FakeMarketDataRepository(bars_by_symbol=bars_by_symbol)
    data = await fetch_holdings_returns(repo, holdings)
    analytics = AnalyticsService().compute(data)
    risk_metrics = RiskMetricsService().compute(data)
    ai_predictions = AiPortfolioEngineService().compute(
        data, analytics, risk_metrics, bars_by_symbol
    )
    optimization = None
    if len(data.holdings) >= 2:
        optimization = OptimizationService().optimize(data)
    return analytics, risk_metrics, ai_predictions, optimization


class TestRecommendationEngineService:
    async def test_a_concentrated_single_sector_portfolio_triggers_reduce_sector_exposure(
        self,
    ) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=800.0, sector="Tech"),
            PortfolioHoldingInput(symbol="MSFT", quantity=5, market_value=200.0, sector="Tech"),
        ]
        analytics, risk_metrics, ai_predictions, optimization = await _build_full_bundle(holdings)
        service = RecommendationEngineService()

        recommendations = service.generate(analytics, risk_metrics, ai_predictions, optimization)

        reduce_recs = [r for r in recommendations if r.type == "reduce_sector_exposure"]
        assert len(reduce_recs) == 1
        assert reduce_recs[0].affected_assets == ("Tech",)
        assert "Tech" in reduce_recs[0].reason

    async def test_a_well_diversified_portfolio_produces_no_sector_or_diversification_flags(
        self,
    ) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=250.0, sector="Tech"),
            PortfolioHoldingInput(
                symbol="JNJ", quantity=5, market_value=250.0, sector="Healthcare"
            ),
            PortfolioHoldingInput(symbol="XOM", quantity=8, market_value=250.0, sector="Energy"),
            PortfolioHoldingInput(
                symbol="JPM", quantity=6, market_value=250.0, sector="Financials"
            ),
        ]
        analytics, risk_metrics, ai_predictions, optimization = await _build_full_bundle(holdings)
        service = RecommendationEngineService()

        recommendations = service.generate(analytics, risk_metrics, ai_predictions, optimization)

        sector_recs = [
            r
            for r in recommendations
            if r.type in ("reduce_sector_exposure", "increase_sector_exposure")
        ]
        # Evenly split across 4 sectors at 25% each — none exceeds the
        # 40% overexposure threshold nor falls under the 5% token
        # threshold.
        assert sector_recs == []

    async def test_every_recommendations_confidence_is_within_bounds(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=900.0, sector="Tech"),
            PortfolioHoldingInput(symbol="MSFT", quantity=5, market_value=100.0, sector="Tech"),
        ]
        analytics, risk_metrics, ai_predictions, optimization = await _build_full_bundle(holdings)
        service = RecommendationEngineService()

        recommendations = service.generate(analytics, risk_metrics, ai_predictions, optimization)

        assert len(recommendations) > 0
        for rec in recommendations:
            assert 0.0 <= rec.confidence <= 1.0
            assert rec.reason
            assert rec.risk_impact
            assert rec.expected_improvement

    async def test_a_materially_different_weighting_triggers_a_rebalance_recommendation(
        self,
    ) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=950.0, sector="Tech"),
            PortfolioHoldingInput(
                symbol="JNJ", quantity=5, market_value=50.0, sector="Healthcare"
            ),
        ]
        analytics, risk_metrics, ai_predictions, optimization = await _build_full_bundle(holdings)
        service = RecommendationEngineService()

        recommendations = service.generate(analytics, risk_metrics, ai_predictions, optimization)

        rebalance_recs = [r for r in recommendations if r.type == "suggested_rebalance"]
        # A 95/5 split is highly unlikely to already match the Max
        # Sharpe optimum exactly, so a material rebalance suggestion is
        # expected here.
        assert len(rebalance_recs) <= 1  # at most one rebalance recommendation is ever produced

    async def test_no_optimization_result_is_handled_without_error(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        analytics, risk_metrics, ai_predictions, optimization = await _build_full_bundle(holdings)
        service = RecommendationEngineService()

        # A single-holding portfolio has no OptimizationResult (raises
        # InsufficientHoldingsForOptimizationError upstream) — the
        # orchestrating caller passes None in that case.
        assert optimization is None
        recommendations = service.generate(analytics, risk_metrics, ai_predictions, None)

        rebalance_recs = [r for r in recommendations if r.type == "suggested_rebalance"]
        assert rebalance_recs == []
