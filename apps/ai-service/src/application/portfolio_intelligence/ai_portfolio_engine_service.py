"""
AiPortfolioEngineService — Phase 10 AI Portfolio Engine.

Produces:
    - Expected Return Prediction
    - Portfolio Risk Prediction
    - Investment Health Prediction
    - Market Exposure Prediction
    - Sector Risk Prediction
    - Portfolio Stability Score
    - Portfolio Confidence Score

Architecture:

    PortfolioIntelligenceUseCase
              │
              ▼
    AiPortfolioEngineService
              │
              ▼
         ModelLoader
              │
              ├── LSTM
              ├── ARIMA
              ├── Prophet
              ├── Random Forest
              ├── XGBoost
              └── FinBERT
              │
              ▼
       DecisionEngine
              │
              ▼
    Per-holding AI decision
              │
              ▼
       Portfolio aggregation

IMPORTANT:

    This service does NOT train models.

    ModelLoader loads the ACTIVE trained model artifacts for each
    portfolio holding symbol.

    DecisionEngine performs inference using those trained models.

    Phase 10 therefore reuses the existing Phase 7 ML infrastructure
    instead of creating new or untrained models.

IMPORTANT CORRECTNESS RULE:

    DecisionEngineResult.price_forecast_1d is a forecast.

    It MUST NOT be used as the current market price.

    The current/latest price used for expected-return calculations
    comes from the actual OHLCV bars already fetched by
    fetch_holdings_returns().
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.application.ml.decision_engine import (
    DecisionEngine,
    DecisionEngineResult,
)
from src.application.portfolio_intelligence.analytics_service import (
    PortfolioAnalytics,
)
from src.application.portfolio_intelligence.data import (
    PortfolioReturnsData,
)
from src.application.portfolio_intelligence.risk_metrics_service import (
    RiskMetrics,
)
from src.domain.ml.repositories import OhlcvBar
from src.infrastructure.ml.model_registry.model_loader import (
    ModelLoader,
)


# ============================================================================
# CONSTANTS
# ============================================================================

WEEKS_PER_YEAR = 52.0

MIN_PRICE = 0.0

NEUTRAL_MARKET_EXPOSURE = 50.0


# ============================================================================
# SECTOR RISK
# ============================================================================


@dataclass(frozen=True, slots=True)
class SectorRiskEntry:
    """
    Portfolio-level sector risk representation.

    risk_score:
        0-100.
        Higher means greater portfolio risk contribution.
    """

    sector: str
    risk_score: float


# ============================================================================
# AI PORTFOLIO PREDICTIONS
# ============================================================================


@dataclass(frozen=True, slots=True)
class AiPortfolioPredictions:
    """
    Complete Phase 10 AI portfolio prediction result.
    """

    expected_return_pct: float
    """
    Forward-looking expected annualized return (%).

    Calculation:

        latest actual close
                ↓
        7-day AI forecast
                ↓
        7-day percentage return
                ↓
        × 52 weeks
                ↓
        portfolio-weighted annualized estimate

    This is a disclosed product formula, not an industry-standard
    expected-return definition.
    """

    portfolio_risk_prediction: float
    """
    0-100.

    Higher = riskier.

    Combines:
        70% historical PortfolioAnalytics risk score
        30% AI signal instability
    """

    investment_health_prediction: float
    """
    0-100.

    Higher = healthier.

    Combines:
        70% historical portfolio health
        30% AI ensemble confidence
    """

    market_exposure_pct: float
    """
    0-100.

    Beta-based market exposure estimate.

    beta = 0.0 -> 0%
    beta = 1.0 -> 50%
    beta = 2.0 -> 100%

    When beta is unavailable, returns 50.0 as a neutral midpoint.
    """

    sector_risk: tuple[SectorRiskEntry, ...]
    """
    Portfolio sector-risk approximation.
    """

    portfolio_stability_score: float
    """
    0-100.

    Higher = stronger agreement among holding-level AI verdicts.
    """

    portfolio_confidence_score: float
    """
    0-100.

    Portfolio-weighted average of existing DecisionEngine
    confidence values.
    """


# ============================================================================
# AI PORTFOLIO ENGINE SERVICE
# ============================================================================


class AiPortfolioEngineService:
    """
    Phase 10 AI Portfolio Engine.

    The service:

        1. Receives already-fetched OHLCV bars.
        2. Loads active trained models through ModelLoader.
        3. Creates a DecisionEngine using those models.
        4. Runs inference for every holding.
        5. Aggregates holding-level results.

    No training occurs here.
    No additional market-data fetch occurs here.
    """

    def __init__(
        self,
        model_loader: ModelLoader,
    ) -> None:
        self._model_loader = model_loader

    async def compute(
        self,
        data: PortfolioReturnsData,
        analytics: PortfolioAnalytics,
        risk_metrics: RiskMetrics,
        bars_by_symbol: dict[str, tuple[OhlcvBar, ...]],
    ) -> AiPortfolioPredictions:
        """
        Compute all Phase 10 AI portfolio predictions.

        bars_by_symbol contains the same OHLCV data already fetched
        by fetch_holdings_returns().

        This prevents a second market-data request.
        """

        decisions: dict[str, DecisionEngineResult] = {}

        # ------------------------------------------------------------------
        # RUN DECISION ENGINE FOR EACH HOLDING
        # ------------------------------------------------------------------

        for holding in data.holdings:
            symbol = _normalize_symbol(holding.symbol)

            if not symbol:
                continue

            # --------------------------------------------------------------
            # SAME OHLCV DATA ALREADY FETCHED BY PORTFOLIO DATA LAYER
            # --------------------------------------------------------------

            bars = _get_bars_for_symbol(
                bars_by_symbol,
                symbol,
            )

            if not bars:
                continue

            # --------------------------------------------------------------
            # LOAD ACTIVE TRAINED MODELS
            # --------------------------------------------------------------

            loaded_models = await self._model_loader.load_all_models(
                symbol
            )

            models = loaded_models.models

            # --------------------------------------------------------------
            # BUILD DECISION ENGINE USING TRAINED MODELS
            # --------------------------------------------------------------

            decision_engine = DecisionEngine(
                lstm=models.get("lstm"),
                arima=models.get("arima"),
                prophet=models.get("prophet"),
                random_forest=models.get("random_forest"),
                xgboost=models.get("xgboost"),
                finbert=models.get("finbert"),
            )

            # --------------------------------------------------------------
            # CONVERT OHLCV BARS TO DATAFRAME
            # --------------------------------------------------------------

            ohlcv = _bars_to_dataframe(bars)

            # --------------------------------------------------------------
            # RUN EXISTING DECISION ENGINE
            # --------------------------------------------------------------

            decisions[symbol] = decision_engine.decide(
                symbol,
                ohlcv,
            )

        # ------------------------------------------------------------------
        # PORTFOLIO-LEVEL AGGREGATION
        # ------------------------------------------------------------------

        expected_return_pct = _expected_return_pct(
            data=data,
            decisions=decisions,
            bars_by_symbol=bars_by_symbol,
        )

        portfolio_confidence_score = _portfolio_confidence_score(
            data=data,
            decisions=decisions,
        )

        portfolio_stability_score = _portfolio_stability_score(
            data=data,
            decisions=decisions,
        )

        portfolio_risk_prediction = _portfolio_risk_prediction(
            risk_score=analytics.risk_score,
            stability_score=portfolio_stability_score,
        )

        investment_health_prediction = _investment_health_prediction(
            health_score=analytics.health_score,
            confidence_score=portfolio_confidence_score,
        )

        market_exposure_pct = _market_exposure_pct(
            risk_metrics.beta,
        )

        sector_risk = _sector_risk(
            analytics,
        )

        return AiPortfolioPredictions(
            expected_return_pct=expected_return_pct,
            portfolio_risk_prediction=portfolio_risk_prediction,
            investment_health_prediction=investment_health_prediction,
            market_exposure_pct=market_exposure_pct,
            sector_risk=sector_risk,
            portfolio_stability_score=portfolio_stability_score,
            portfolio_confidence_score=portfolio_confidence_score,
        )


# ============================================================================
# HELPERS
# ============================================================================


def _normalize_symbol(symbol: str) -> str:
    """
    Normalize a portfolio ticker symbol.
    """

    return symbol.strip().upper()


def _get_bars_for_symbol(
    bars_by_symbol: dict[str, tuple[OhlcvBar, ...]],
    symbol: str,
) -> tuple[OhlcvBar, ...]:
    """
    Retrieve bars defensively.

    The primary lookup uses the normalized symbol.

    A fallback lookup handles callers that may have populated the
    dictionary using a differently-cased symbol.
    """

    bars = bars_by_symbol.get(symbol)

    if bars:
        return bars

    for key, candidate_bars in bars_by_symbol.items():
        if _normalize_symbol(key) == symbol:
            return candidate_bars

    return ()


def _bars_to_dataframe(
    bars: tuple[OhlcvBar, ...],
) -> pd.DataFrame:
    """
    Convert OhlcvBar objects to the DataFrame expected by DecisionEngine.
    """

    return pd.DataFrame(
        {
            "open": [bar.open for bar in bars],
            "high": [bar.high for bar in bars],
            "low": [bar.low for bar in bars],
            "close": [bar.close for bar in bars],
            "volume": [bar.volume for bar in bars],
        }
    )


# ============================================================================
# EXPECTED RETURN
# ============================================================================


def _expected_return_pct(
    data: PortfolioReturnsData,
    decisions: dict[str, DecisionEngineResult],
    bars_by_symbol: dict[str, tuple[OhlcvBar, ...]],
) -> float:
    """
    Calculate the portfolio-weighted forward expected return.

    IMPORTANT:

        The latest actual close comes from OHLCV market data.

        It does NOT come from:
            decision.price_forecast_1d

    For each holding:

        latest actual close
                    ↓
        DecisionEngine 7-day forecast
                    ↓
        7-day percentage return
                    ↓
        × 52
                    ↓
        annualized estimate
                    ↓
        portfolio weighting

    Example:

        current price = 305.26
        7-day forecast = 313.3864

        weekly return =
            (313.3864 - 305.26) / 305.26 × 100

        annualized estimate =
            weekly return × 52

    Holdings without valid market data or AI decisions are excluded,
    and remaining weights are normalized.
    """

    total_weight = 0.0
    weighted_sum = 0.0

    for holding in data.holdings:
        symbol = _normalize_symbol(holding.symbol)

        if not symbol:
            continue

        decision = decisions.get(symbol)

        if decision is None:
            continue

        bars = _get_bars_for_symbol(
            bars_by_symbol,
            symbol,
        )

        if not bars:
            continue

        # --------------------------------------------------------------
        # CRITICAL:
        # Use the latest REAL market close.
        # Do NOT use decision.price_forecast_1d.
        # --------------------------------------------------------------

        latest_close = float(bars[-1].close)

        forecast_7d = float(
            decision.price_forecast_7d
        )

        if latest_close <= MIN_PRICE:
            continue

        # --------------------------------------------------------------
        # 7-DAY FORECAST RETURN
        # --------------------------------------------------------------

        weekly_change_pct = (
            (forecast_7d - latest_close)
            / latest_close
            * 100.0
        )

        # --------------------------------------------------------------
        # SIMPLE ANNUALIZED FORECAST
        #
        # This is the disclosed Phase 10 product formula.
        # It is not a claim that returns compound at this rate.
        # --------------------------------------------------------------

        annualized_estimate = (
            weekly_change_pct
            * WEEKS_PER_YEAR
        )

        weight = float(holding.weight)

        if weight <= 0.0:
            continue

        weighted_sum += (
            annualized_estimate
            * weight
        )

        total_weight += weight

    if total_weight <= 0.0:
        return 0.0

    return round(
        weighted_sum / total_weight,
        2,
    )


# ============================================================================
# PORTFOLIO CONFIDENCE
# ============================================================================


def _portfolio_confidence_score(
    data: PortfolioReturnsData,
    decisions: dict[str, DecisionEngineResult],
) -> float:
    """
    Portfolio-weighted DecisionEngine confidence.

    DecisionEngine confidence:
        0-1

    Portfolio confidence:
        0-100
    """

    total_weight = 0.0
    weighted_sum = 0.0

    for holding in data.holdings:
        symbol = _normalize_symbol(holding.symbol)

        decision = decisions.get(symbol)

        if decision is None:
            continue

        confidence = float(
            decision.recommendation.confidence.value
        )

        weight = float(holding.weight)

        if weight <= 0.0:
            continue

        weighted_sum += confidence * weight
        total_weight += weight

    if total_weight <= 0.0:
        return 0.0

    return round(
        (
            weighted_sum
            / total_weight
        )
        * 100.0,
        2,
    )


# ============================================================================
# PORTFOLIO STABILITY
# ============================================================================


def _portfolio_stability_score(
    data: PortfolioReturnsData,
    decisions: dict[str, DecisionEngineResult],
) -> float:
    """
    Measure agreement between holding-level AI verdicts.

    Example:

        BUY 80%
        BUY 20%

        => 100% stability

    Example:

        BUY 40%
        SELL 40%
        HOLD 20%

        => 40% stability

    This measures AI signal agreement, not price volatility.
    """

    if not data.holdings:
        return 0.0

    verdict_weights: dict[str, float] = {
        "buy": 0.0,
        "sell": 0.0,
        "hold": 0.0,
    }

    total_weight = 0.0

    for holding in data.holdings:
        symbol = _normalize_symbol(holding.symbol)

        decision = decisions.get(symbol)

        if decision is None:
            continue

        verdict = str(
            decision.recommendation.verdict
        ).lower()

        if verdict not in verdict_weights:
            continue

        weight = float(holding.weight)

        if weight <= 0.0:
            continue

        verdict_weights[verdict] += weight
        total_weight += weight

    if total_weight <= 0.0:
        return 0.0

    dominant_share = (
        max(verdict_weights.values())
        / total_weight
    )

    return round(
        dominant_share * 100.0,
        2,
    )


# ============================================================================
# PORTFOLIO RISK PREDICTION
# ============================================================================


def _portfolio_risk_prediction(
    risk_score: float,
    stability_score: float,
) -> float:
    """
    Forward-looking portfolio risk prediction.

    Disclosed Phase 10 formula:

        70% historical risk score
        +
        30% AI signal instability

    Instability:

        100 - stability_score

    Result:
        0-100
    """

    instability = max(
        0.0,
        min(
            100.0,
            100.0 - stability_score,
        ),
    )

    risk = (
        float(risk_score) * 0.70
        + instability * 0.30
    )

    return round(
        max(
            0.0,
            min(
                100.0,
                risk,
            ),
        ),
        2,
    )


# ============================================================================
# INVESTMENT HEALTH PREDICTION
# ============================================================================


def _investment_health_prediction(
    health_score: float,
    confidence_score: float,
) -> float:
    """
    Forward-looking portfolio health prediction.

    Disclosed Phase 10 formula:

        70% historical health score
        +
        30% AI confidence
    """

    health = (
        float(health_score) * 0.70
        + float(confidence_score) * 0.30
    )

    return round(
        max(
            0.0,
            min(
                100.0,
                health,
            ),
        ),
        2,
    )


# ============================================================================
# MARKET EXPOSURE
# ============================================================================


def _market_exposure_pct(
    beta: float | None,
) -> float:
    """
    Convert beta to the disclosed Phase 10 market-exposure scale.

        beta = 0.0 -> 0%
        beta = 1.0 -> 50%
        beta = 2.0 -> 100%

    If beta is unavailable:

        50%

    is returned as the documented neutral midpoint.

    This is a product-specific mapping, not a textbook definition
    of market exposure.
    """

    if beta is None:
        return NEUTRAL_MARKET_EXPOSURE

    exposure = float(beta) * 50.0

    return round(
        max(
            0.0,
            min(
                100.0,
                exposure,
            ),
        ),
        2,
    )


# ============================================================================
# SECTOR RISK
# ============================================================================


def _sector_risk(
    analytics: PortfolioAnalytics,
) -> tuple[SectorRiskEntry, ...]:
    """
    Calculate the disclosed Phase 10 sector-risk approximation.

    Formula:

        portfolio risk score
            ×
        sector allocation %
            /
        100

    Example:

        portfolio risk = 65
        Technology allocation = 100%

        sector risk = 65

    This is NOT a true sector volatility/correlation decomposition.
    """

    return tuple(
        SectorRiskEntry(
            sector=entry.sector,
            risk_score=round(
                float(analytics.risk_score)
                * (
                    float(entry.allocation_pct)
                    / 100.0
                ),
                2,
            ),
        )
        for entry in analytics.sector_exposure
    )