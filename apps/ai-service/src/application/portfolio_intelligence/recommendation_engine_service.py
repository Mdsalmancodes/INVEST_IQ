"""RecommendationEngineService — Phase 10 AI Recommendation Engine with
Explainable AI.

CONSUMES the already-computed outputs of Tasks 3/4/5/7
(PortfolioAnalytics, RiskMetrics, AiPortfolioPredictions,
OptimizationResult) rather than computing anything new from raw market
data — this service's only job is deciding WHICH recommendations to
surface and generating their human-readable explanation, not
recalculating any of the underlying numbers.

EVERY TRIGGER THRESHOLD BELOW IS A DISCLOSED DEFAULT, matching the exact
same "document the considered choice, don't fabricate false authority"
treatment already established for analytics_service.py's Health/
Diversification/Risk Scores — no existing spec in this codebase defines
these specific thresholds.

EXPLAINABLE AI CONTRACT: every Recommendation carries reason (a real
generated sentence referencing the actual numbers that triggered it,
not a static template with no substitution), risk_impact, expected_improvement,
confidence (0.0-1.0), and affected_assets — per the founder's own
explicit Explainable AI requirement list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.application.portfolio_intelligence.ai_portfolio_engine_service import (
    AiPortfolioPredictions,
)
from src.application.portfolio_intelligence.analytics_service import PortfolioAnalytics
from src.application.portfolio_intelligence.optimization_service import OptimizationResult
from src.application.portfolio_intelligence.risk_metrics_service import RiskMetrics

RecommendationType = Literal[
    "reduce_sector_exposure",
    "increase_sector_exposure",
    "over_diversified",
    "under_diversified",
    "risk_exceeds_target",
    "suggested_rebalance",
]

# DISCLOSED DEFAULT THRESHOLDS — every one a considered choice, not an
# industry-mandated number:
_SECTOR_OVEREXPOSURE_THRESHOLD_PCT = 40.0
"""A single sector exceeding 40% of the portfolio triggers a "reduce"
recommendation — a common concentration-risk guidance rule of thumb
(no single sector bet should dominate a diversified portfolio), chosen
as a round, defensible number rather than derived from any specific
academic source."""
_SECTOR_UNDEREXPOSURE_THRESHOLD_PCT = 5.0
"""A sector with a NONZERO but very small allocation (below 5%) is
flagged as a candidate to either increase or consolidate — prevents
recommending a meaningless "increase Healthcare from 4.9% to 5.1%" for
every tiny position, while still catching genuinely token allocations."""
_OVER_DIVERSIFIED_SCORE_THRESHOLD = 90.0
"""A diversification_score above 90 is flagged as POSSIBLY over-
diversified — spreading a portfolio extremely thin can dilute
meaningful returns without materially reducing risk further (the
well-known "diminishing returns to diversification" effect) — 90 is a
disclosed high bar, not triggered by an already-healthy 70-80 score."""
_UNDER_DIVERSIFIED_SCORE_THRESHOLD = 40.0
"""A diversification_score below 40 is flagged as under-diversified."""
_RISK_EXCEEDS_TARGET_THRESHOLD = 70.0
"""A risk_score (or the AI Engine's own forward-looking
portfolio_risk_prediction) above 70/100 is flagged as exceeding a
disclosed target risk tolerance — a considered "moderate-to-aggressive"
cutoff, not user-configurable in this phase (see known-issues.md)."""
_REBALANCE_MATERIALITY_THRESHOLD_PCT = 5.0
"""A suggested weight delta must exceed 5 percentage points in
magnitude to surface as a recommendation — avoids recommending trivial
rebalances (e.g. "sell 0.3% of AAPL") that aren't worth the
transaction-cost/effort tradeoff for a retail investor."""


@dataclass(frozen=True, slots=True)
class Recommendation:
    type: RecommendationType
    reason: str
    risk_impact: str
    expected_improvement: str
    confidence: float
    affected_assets: tuple[str, ...]


class RecommendationEngineService:
    def generate(
        self,
        analytics: PortfolioAnalytics,
        risk_metrics: RiskMetrics,
        ai_predictions: AiPortfolioPredictions,
        optimization: OptimizationResult | None,
    ) -> tuple[Recommendation, ...]:
        """`optimization` is optional — OptimizationService.optimize()
        raises for <2 holdings (see optimization_service.py), so a
        single-holding portfolio genuinely has no optimization result
        to derive a rebalance recommendation from; this service must
        still produce sector/diversification/risk recommendations for
        such a portfolio without crashing."""
        recommendations: list[Recommendation] = []
        recommendations.extend(_sector_exposure_recommendations(analytics))
        recommendations.extend(_diversification_recommendations(analytics))
        recommendations.extend(_risk_recommendations(analytics, ai_predictions))
        if optimization is not None:
            recommendations.extend(_rebalancing_recommendations(optimization))
        return tuple(recommendations)


def _sector_exposure_recommendations(analytics: PortfolioAnalytics) -> list[Recommendation]:
    recommendations: list[Recommendation] = []
    for entry in analytics.sector_exposure:
        if entry.allocation_pct > _SECTOR_OVEREXPOSURE_THRESHOLD_PCT:
            excess = entry.allocation_pct - _SECTOR_OVEREXPOSURE_THRESHOLD_PCT
            recommendations.append(
                Recommendation(
                    type="reduce_sector_exposure",
                    reason=(
                        f"{entry.sector} makes up {entry.allocation_pct:.1f}% of the portfolio, "
                        f"exceeding the {_SECTOR_OVEREXPOSURE_THRESHOLD_PCT:.0f}% concentration "
                        f"guideline by {excess:.1f} percentage points."
                    ),
                    risk_impact=(
                        "A single-sector downturn would have an outsized impact on the "
                        "portfolio's overall value."
                    ),
                    expected_improvement=(
                        f"Trimming {entry.sector} toward "
                        f"{_SECTOR_OVEREXPOSURE_THRESHOLD_PCT:.0f}% would reduce concentration "
                        "risk without requiring a full liquidation."
                    ),
                    confidence=min(1.0, 0.5 + excess / 100.0),
                    affected_assets=(entry.sector,),
                )
            )
        elif 0.0 < entry.allocation_pct < _SECTOR_UNDEREXPOSURE_THRESHOLD_PCT:
            recommendations.append(
                Recommendation(
                    type="increase_sector_exposure",
                    reason=(
                        f"{entry.sector} represents only {entry.allocation_pct:.1f}% of the "
                        "portfolio — a token allocation with limited impact either way."
                    ),
                    risk_impact=(
                        "Minimal — this sector's current small size means either increasing "
                        "or exiting it would not materially change overall portfolio risk."
                    ),
                    expected_improvement=(
                        "Consolidating very small positions can reduce tracking overhead "
                        "without a meaningful change in diversification."
                    ),
                    confidence=0.4,
                    affected_assets=(entry.sector,),
                )
            )
    return recommendations


def _diversification_recommendations(analytics: PortfolioAnalytics) -> list[Recommendation]:
    score = analytics.diversification_score
    symbols = tuple(entry.symbol for entry in analytics.asset_allocation)
    if score > _OVER_DIVERSIFIED_SCORE_THRESHOLD:
        return [
            Recommendation(
                type="over_diversified",
                reason=(
                    f"The portfolio's diversification score is {score:.1f}/100, above the "
                    f"{_OVER_DIVERSIFIED_SCORE_THRESHOLD:.0f} threshold where additional "
                    "spreading tends to dilute returns more than it reduces risk."
                ),
                risk_impact=(
                    "Low — the portfolio is already well-protected against single-holding risk."
                ),
                expected_improvement=(
                    "Consolidating into fewer, higher-conviction positions may improve "
                    "returns without materially increasing risk."
                ),
                confidence=min(1.0, (score - _OVER_DIVERSIFIED_SCORE_THRESHOLD) / 10.0),
                affected_assets=symbols,
            )
        ]
    if score < _UNDER_DIVERSIFIED_SCORE_THRESHOLD:
        return [
            Recommendation(
                type="under_diversified",
                reason=(
                    f"The portfolio's diversification score is {score:.1f}/100, below the "
                    f"{_UNDER_DIVERSIFIED_SCORE_THRESHOLD:.0f} threshold indicating meaningful "
                    "concentration risk."
                ),
                risk_impact=(
                    "High — a small number of holdings or sectors currently drive most of "
                    "the portfolio's overall risk."
                ),
                expected_improvement=(
                    "Adding holdings across additional sectors or asset classes would "
                    "reduce reliance on any single position."
                ),
                confidence=min(1.0, (_UNDER_DIVERSIFIED_SCORE_THRESHOLD - score) / 20.0),
                affected_assets=symbols,
            )
        ]
    return []


def _risk_recommendations(
    analytics: PortfolioAnalytics, ai_predictions: AiPortfolioPredictions
) -> list[Recommendation]:
    # Uses the more forward-looking portfolio_risk_prediction when
    # available, falling back to the historical risk_score — both are on
    # the same 0-100 scale (disclosed in ai_portfolio_engine_service.py).
    effective_risk = max(analytics.risk_score, ai_predictions.portfolio_risk_prediction)
    if effective_risk <= _RISK_EXCEEDS_TARGET_THRESHOLD:
        return []
    excess = effective_risk - _RISK_EXCEEDS_TARGET_THRESHOLD
    symbols = tuple(entry.symbol for entry in analytics.asset_allocation)
    return [
        Recommendation(
            type="risk_exceeds_target",
            reason=(
                f"The portfolio's risk score is {effective_risk:.1f}/100, exceeding the "
                f"{_RISK_EXCEEDS_TARGET_THRESHOLD:.0f} target risk tolerance by "
                f"{excess:.1f} points."
            ),
            risk_impact=(
                "The portfolio is likely to experience larger swings in value than a "
                "moderate-risk target would suggest."
            ),
            expected_improvement=(
                "Reducing concentration in the highest-weighted or most volatile holdings "
                "would bring overall risk closer to target."
            ),
            confidence=min(1.0, excess / 30.0),
            affected_assets=symbols,
        )
    ]


def _rebalancing_recommendations(optimization: OptimizationResult) -> list[Recommendation]:
    material_suggestions = [
        s
        for s in optimization.suggested_rebalancing
        if abs(s.delta_pct) > _REBALANCE_MATERIALITY_THRESHOLD_PCT
    ]
    if not material_suggestions:
        return []
    affected = tuple(s.symbol for s in material_suggestions)
    direction_summary = "; ".join(
        f"{s.symbol} {'increase' if s.delta_pct > 0 else 'decrease'} by {abs(s.delta_pct):.1f}pp"
        for s in material_suggestions
    )
    max_delta = max(abs(s.delta_pct) for s in material_suggestions)
    return [
        Recommendation(
            type="suggested_rebalance",
            reason=(
                "The current portfolio weights differ materially from the Maximum Sharpe "
                f"optimized allocation: {direction_summary}."
            ),
            risk_impact=(
                f"Rebalancing toward the optimized weights would change expected volatility "
                f"to {optimization.max_sharpe_portfolio.volatility_pct:.1f}% (annualized)."
            ),
            expected_improvement=(
                f"The optimized allocation targets a Sharpe ratio of "
                f"{optimization.max_sharpe_portfolio.sharpe_ratio:.2f}, versus the current "
                "portfolio's own risk-adjusted return."
            ),
            confidence=min(1.0, max_delta / 50.0),
            affected_assets=affected,
        )
    ]
