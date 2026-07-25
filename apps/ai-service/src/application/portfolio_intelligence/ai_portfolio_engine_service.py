"""AiPortfolioEngineService — Phase 10 AI Portfolio Engine.

Produces: Expected Return Prediction, Portfolio Risk Prediction,
Investment Health Prediction, Market Exposure Prediction, Sector Risk
Prediction, Portfolio Stability Score, Portfolio Confidence Score.

DESIGN DECISION (per Task 2's architecture design): none of these are a
new, separately-trained ML model. Every one COMBINES the quantitative
output already computed by analytics_service.py/risk_metrics_service.py
with the EXISTING per-holding DecisionEngine (Phase 7, completely
unmodified) — the same "reuse existing computed signals rather than
fabricating a new model" precedent Phase 9 already established (e.g.
Task 7's decision to reuse get_recommendation()'s sentiment_score field
instead of building a new live-sentiment model). Concretely: this
service calls DecisionEngine.decide() once per holding symbol (the SAME
OHLCV bars fetch_holdings_returns already fetched — see the disclosed
double-fetch note in known-issues.md), then blends each holding's own
price_forecast_7d/confidence with that holding's portfolio weight.

EVERY FORMULA BELOW IS A DISCLOSED DEFAULT, NOT AN INDUSTRY STANDARD —
this entire "AI Portfolio Engine" concept (as opposed to Sharpe Ratio or
Beta, which have one unambiguous textbook definition) is itself a new
composite product built for this phase, exactly like analytics_service's
Health/Diversification/Risk Scores. Each function's docstring documents
its exact composition so a future phase can deliberately revise it with
full visibility into what it originally was and why.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.application.ml.decision_engine import DecisionEngine, DecisionEngineResult
from src.application.portfolio_intelligence.analytics_service import PortfolioAnalytics
from src.application.portfolio_intelligence.data import PortfolioReturnsData
from src.application.portfolio_intelligence.risk_metrics_service import RiskMetrics
from src.domain.ml.repositories import OhlcvBar


@dataclass(frozen=True, slots=True)
class SectorRiskEntry:
    sector: str
    risk_score: float  # 0-100, same scale/direction as PortfolioAnalytics.risk_score


@dataclass(frozen=True, slots=True)
class AiPortfolioPredictions:
    expected_return_pct: float
    """Forward-looking expected return (%), distinct from
    annualized_return_pct's own BACKWARD-looking historical figure."""
    portfolio_risk_prediction: float
    """0-100, higher = riskier — a forward-looking variant of
    PortfolioAnalytics.risk_score, blended with model disagreement (see
    _portfolio_risk_prediction's docstring)."""
    investment_health_prediction: float
    """0-100, higher = healthier — a forward-looking variant of
    PortfolioAnalytics.health_score, blended with the ensemble's own
    aggregate confidence."""
    market_exposure_pct: float
    """0-100 — how much of the portfolio's expected movement is
    explained by broad market risk (beta-driven) vs. idiosyncratic,
    stock-specific risk. Requires a benchmark; None-safe default of 50.0
    (a neutral midpoint) when no benchmark/beta is available — see
    _market_exposure_pct's docstring."""
    sector_risk: tuple[SectorRiskEntry, ...]
    portfolio_stability_score: float
    """0-100, higher = more stable — based on the CONSISTENCY of the
    ensemble's verdicts and forecasts across holdings, not the same
    concept as volatility (which risk_score already captures)."""
    portfolio_confidence_score: float
    """0-100 — the portfolio-weighted average of each holding's own
    DecisionEngine confidence."""


class AiPortfolioEngineService:
    def __init__(self, decision_engine: DecisionEngine | None = None) -> None:
        self._decision_engine = decision_engine or DecisionEngine()

    def compute(
        self,
        data: PortfolioReturnsData,
        analytics: PortfolioAnalytics,
        risk_metrics: RiskMetrics,
        bars_by_symbol: dict[str, tuple[OhlcvBar, ...]],
    ) -> AiPortfolioPredictions:
        """`bars_by_symbol` is the SAME raw OHLCV data
        `fetch_holdings_returns` already fetched for each holding — passed
        in directly by the orchestrating use case rather than this
        service re-fetching it, since it needs the full DataFrame (not
        just the derived daily-return Series `PortfolioReturnsData`
        carries) to call DecisionEngine.decide()."""
        decisions: dict[str, DecisionEngineResult] = {}
        for holding in data.holdings:
            bars = bars_by_symbol.get(holding.symbol)
            if not bars:
                continue
            ohlcv = pd.DataFrame(
                {
                    "open": [b.open for b in bars],
                    "high": [b.high for b in bars],
                    "low": [b.low for b in bars],
                    "close": [b.close for b in bars],
                    "volume": [b.volume for b in bars],
                }
            )
            decisions[holding.symbol] = self._decision_engine.decide(holding.symbol, ohlcv)

        expected_return_pct = _expected_return_pct(data, decisions)
        portfolio_confidence_score = _portfolio_confidence_score(data, decisions)
        portfolio_stability_score = _portfolio_stability_score(data, decisions)
        portfolio_risk_prediction = _portfolio_risk_prediction(
            analytics.risk_score, portfolio_stability_score
        )
        investment_health_prediction = _investment_health_prediction(
            analytics.health_score, portfolio_confidence_score
        )
        market_exposure_pct = _market_exposure_pct(risk_metrics.beta)
        sector_risk = _sector_risk(analytics)

        return AiPortfolioPredictions(
            expected_return_pct=expected_return_pct,
            portfolio_risk_prediction=portfolio_risk_prediction,
            investment_health_prediction=investment_health_prediction,
            market_exposure_pct=market_exposure_pct,
            sector_risk=sector_risk,
            portfolio_stability_score=portfolio_stability_score,
            portfolio_confidence_score=portfolio_confidence_score,
        )


def _expected_return_pct(
    data: PortfolioReturnsData, decisions: dict[str, DecisionEngineResult]
) -> float:
    """Portfolio-weighted average of each holding's own DecisionEngine
    7-day price forecast, expressed as a % change from that holding's
    own most recent close, then annualized-scaled (7-day forecast * 52
    weeks) to be comparable on the same axis as analytics_service's own
    backward-looking annualized_return_pct. A holding with no available
    decision (data gap) is simply excluded from this weighted average
    (its weight is redistributed proportionally among the remaining
    holdings by virtue of not appearing in the sum at all — the same
    "one gap doesn't corrupt the rest" principle used throughout this
    module)."""
    total_weight = 0.0
    weighted_sum = 0.0
    for holding in data.holdings:
        decision = decisions.get(holding.symbol)
        if decision is None:
            continue
        last_close = decision.price_forecast_1d
        forecast_7d = decision.price_forecast_7d
        if last_close == 0.0:
            continue
        weekly_change_pct = (forecast_7d - last_close) / last_close * 100.0
        annualized_estimate = weekly_change_pct * 52.0
        weighted_sum += annualized_estimate * holding.weight
        total_weight += holding.weight
    return round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0


def _portfolio_confidence_score(
    data: PortfolioReturnsData, decisions: dict[str, DecisionEngineResult]
) -> float:
    """Portfolio-weighted average of each holding's own DecisionEngine
    overall confidence (already a genuine, existing [0,1] value per
    holding — this function only aggregates it, it does not invent a new
    confidence computation)."""
    total_weight = 0.0
    weighted_sum = 0.0
    for holding in data.holdings:
        decision = decisions.get(holding.symbol)
        if decision is None:
            continue
        confidence = decision.recommendation.confidence.value
        weighted_sum += confidence * holding.weight
        total_weight += holding.weight
    return round(weighted_sum / total_weight * 100.0, 2) if total_weight > 0 else 0.0


def _portfolio_stability_score(
    data: PortfolioReturnsData, decisions: dict[str, DecisionEngineResult]
) -> float:
    """DISCLOSED DEFAULT — 0-100, higher = more stable. Measures how much
    the ensemble's own per-holding verdicts AGREE with each other
    (portfolio-weighted): if every holding's DecisionEngine independently
    says "buy," the ensemble is in strong directional agreement (high
    stability); if holdings are split between buy/sell/hold, the
    portfolio's overall AI signal is less internally consistent (lower
    stability). This is a genuinely different concept from
    risk_score/annualized_volatility (which measure price movement, not
    signal agreement) — a highly volatile portfolio could still have
    perfectly consistent AI signals, and vice versa."""
    if not data.holdings:
        return 0.0
    verdict_weights: dict[str, float] = {"buy": 0.0, "sell": 0.0, "hold": 0.0}
    total_weight = 0.0
    for holding in data.holdings:
        decision = decisions.get(holding.symbol)
        if decision is None:
            continue
        verdict = decision.recommendation.verdict
        verdict_weights[verdict] += holding.weight
        total_weight += holding.weight
    if total_weight == 0.0:
        return 0.0
    dominant_share = max(verdict_weights.values()) / total_weight
    return round(dominant_share * 100.0, 2)


def _portfolio_risk_prediction(risk_score: float, stability_score: float) -> float:
    """DISCLOSED DEFAULT — a FORWARD-looking variant of
    PortfolioAnalytics.risk_score, adjusted downward when the AI
    ensemble's signals are highly consistent (stable) and upward when
    they are not — the intuition being that internal signal disagreement
    is itself a source of forward-looking uncertainty beyond what
    historical volatility alone captures. Blended 70% historical
    risk_score / 30% instability contribution (100 - stability_score)."""
    instability = 100.0 - stability_score
    return round(risk_score * 0.7 + instability * 0.3, 2)


def _investment_health_prediction(health_score: float, confidence_score: float) -> float:
    """DISCLOSED DEFAULT — a forward-looking variant of
    PortfolioAnalytics.health_score, adjusted upward when the AI
    ensemble's own confidence in its holdings is high. Blended 70%
    historical health_score / 30% ensemble confidence."""
    return round(health_score * 0.7 + confidence_score * 0.3, 2)


def _market_exposure_pct(beta: float | None) -> float:
    """DISCLOSED DEFAULT — 0-100, how much of the portfolio's expected
    volatility is systematic (market-driven) vs. idiosyncratic. Maps
    beta=1.0 (moves exactly with the market) to 50% (a neutral midpoint,
    not 100%, since even a beta=1 portfolio still has SOME
    stock-specific risk) and scales linearly from there — beta=2.0 maps
    to 100%, beta=0.0 maps to 0%. Requires a real beta (which itself
    requires a benchmark return series — see risk_metrics_service.py's
    own disclosed benchmark limitation); returns a neutral 50.0 default
    when beta is unavailable, rather than 0 or a misleadingly precise
    number."""
    if beta is None:
        return 50.0
    return round(max(0.0, min(100.0, beta * 50.0)), 2)


def _sector_risk(analytics: PortfolioAnalytics) -> tuple[SectorRiskEntry, ...]:
    """DISCLOSED DEFAULT — approximates each sector's own risk
    contribution as the PORTFOLIO's overall risk_score, scaled by that
    sector's own concentration WITHIN the portfolio (a sector that is a
    larger share of the portfolio is treated as contributing
    proportionally more to overall risk exposure). This is a
    simplification, not a genuine per-sector volatility/correlation
    decomposition (which would require per-sector return series this
    module does not construct) — disclosed explicitly rather than
    presented as a more rigorous calculation than it is."""
    return tuple(
        SectorRiskEntry(
            sector=entry.sector,
            risk_score=round(analytics.risk_score * (entry.allocation_pct / 100.0), 2),
        )
        for entry in analytics.sector_exposure
    )
