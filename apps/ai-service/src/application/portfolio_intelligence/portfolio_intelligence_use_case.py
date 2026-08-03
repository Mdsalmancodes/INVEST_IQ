"""PortfolioIntelligenceUseCase — orchestrates the Phase 10 quantitative
services (AnalyticsService, RiskMetricsService, AiPortfolioEngineService,
OptimizationService, MonteCarloService, RecommendationEngineService) into
a single callable, mirroring the EXISTING
`portfolio_recommendation_use_case.py`'s own orchestration pattern
(fetch market data via the shared MarketDataRepository Protocol -> run
the domain computation -> return a plain result object) rather than
introducing a new pattern.

This is the integration step the Phase 10 service layer was missing:
every service below (`analytics_service.py`, `risk_metrics_service.py`,
`ai_portfolio_engine_service.py`, `optimization_service.py`,
`monte_carlo_service.py`, `recommendation_engine_service.py`) already
existed, fully implemented and unit-tested, but nothing in `src/` ever
constructed them together and called them in sequence outside their own
test files. This use case is that missing orchestrator — it does not
change, duplicate, or reimplement any of their logic; it reuses the
EXISTING `fetch_holdings_returns()` helper (data.py) for the one shared
fetch-and-derive step every Phase 10 use case needs.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.portfolio_intelligence.ai_portfolio_engine_service import (
    AiPortfolioEngineService,
    AiPortfolioPredictions,
)
from src.application.portfolio_intelligence.analytics_service import (
    AnalyticsService,
    PortfolioAnalytics,
)
from src.application.portfolio_intelligence.data import (
    PortfolioHoldingInput,
    fetch_holdings_returns,
)
from src.application.portfolio_intelligence.monte_carlo_service import (
    MonteCarloResult,
    MonteCarloService,
)
from src.application.portfolio_intelligence.optimization_service import (
    InsufficientHoldingsForOptimizationError,
    OptimizationResult,
    OptimizationService,
)
from src.application.portfolio_intelligence.recommendation_engine_service import (
    Recommendation,
    RecommendationEngineService,
)
from src.application.portfolio_intelligence.risk_metrics_service import (
    RiskMetrics,
    RiskMetricsService,
)
from src.domain.ml.repositories import MarketDataRepository, OhlcvBar


@dataclass(frozen=True, slots=True)
class PortfolioIntelligenceResult:
    analytics: PortfolioAnalytics
    risk_metrics: RiskMetrics
    ai_predictions: AiPortfolioPredictions
    optimization: OptimizationResult | None
    """None for a single-holding portfolio — OptimizationService.optimize()
    is mathematically undefined for fewer than 2 holdings (see
    InsufficientHoldingsForOptimizationError); this use case catches that
    specific, expected condition rather than letting it propagate as a
    500, matching RecommendationEngineService.generate()'s own existing
    "optimization is optional" contract."""
    recommendations: tuple[Recommendation, ...]


class PortfolioIntelligenceUseCase:
    def __init__(
        self,
        market_data_repository: MarketDataRepository,
        analytics_service: AnalyticsService | None = None,
        risk_metrics_service: RiskMetricsService | None = None,
        ai_portfolio_engine_service: AiPortfolioEngineService | None = None,
        optimization_service: OptimizationService | None = None,
        recommendation_engine_service: RecommendationEngineService | None = None,
    ) -> None:
        self._market_data_repository = market_data_repository
        self._analytics_service = analytics_service or AnalyticsService()
        self._risk_metrics_service = risk_metrics_service or RiskMetricsService()
        self._ai_portfolio_engine_service = (
            ai_portfolio_engine_service or AiPortfolioEngineService()
        )
        self._optimization_service = optimization_service or OptimizationService()
        self._recommendation_engine_service = (
            recommendation_engine_service or RecommendationEngineService()
        )

    async def execute(
        self,
        holdings: list[PortfolioHoldingInput],
        lookback_days: int = 400,
    ) -> PortfolioIntelligenceResult:
        bars_by_symbol: dict[str, tuple[OhlcvBar, ...]] = {}
        data = await fetch_holdings_returns(
            self._market_data_repository, holdings, lookback_days, bars_out=bars_by_symbol
        )

        analytics = self._analytics_service.compute(data)
        risk_metrics = self._risk_metrics_service.compute(data)
        ai_predictions = self._ai_portfolio_engine_service.compute(
            data, analytics, risk_metrics, bars_by_symbol
        )

        optimization: OptimizationResult | None
        try:
            optimization = self._optimization_service.optimize(data)
        except InsufficientHoldingsForOptimizationError:
            optimization = None

        recommendations = self._recommendation_engine_service.generate(
            analytics, risk_metrics, ai_predictions, optimization
        )

        return PortfolioIntelligenceResult(
            analytics=analytics,
            risk_metrics=risk_metrics,
            ai_predictions=ai_predictions,
            optimization=optimization,
            recommendations=recommendations,
        )


class MonteCarloUseCase:
    """Split from PortfolioIntelligenceUseCase (rather than folded into
    one mega-use-case) since Monte Carlo simulation is parameterized by
    `num_runs`/`horizon_days` per-call and is meaningfully expensive (up
    to 5000 runs) — a caller who only wants analytics/risk/optimization/
    recommendations should not pay for a simulation they did not ask
    for, and vice versa."""

    def __init__(
        self,
        market_data_repository: MarketDataRepository,
        monte_carlo_service: MonteCarloService | None = None,
    ) -> None:
        self._market_data_repository = market_data_repository
        self._monte_carlo_service = monte_carlo_service or MonteCarloService()

    async def execute(
        self,
        holdings: list[PortfolioHoldingInput],
        num_runs: int,
        horizon_days: int,
        lookback_days: int = 400,
    ) -> MonteCarloResult:
        data = await fetch_holdings_returns(self._market_data_repository, holdings, lookback_days)
        return self._monte_carlo_service.simulate(
            data, num_runs=num_runs, horizon_days=horizon_days
        )
