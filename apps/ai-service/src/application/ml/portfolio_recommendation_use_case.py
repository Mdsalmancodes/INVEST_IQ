"""
PortfolioRecommendationUseCase
================================

Application use case for portfolio-level investment recommendations.

Architecture
------------

PortfolioRecommendationUseCase
            |
            v
      PredictUseCase
            |
            v
      MarketDataRepository
            |
            v
        ModelLoader
            |
            v
    Active trained models
            |
            v
      DecisionEngine
            |
            v
    BUY / SELL / HOLD
            |
            v
 Portfolio aggregation


IMPORTANT
---------

Do NOT instantiate DecisionEngine directly in this use case.

The PredictUseCase already owns the complete trained-model
inference pipeline, including:

    - real market data retrieval
    - active model loading
    - model artifact loading
    - model-version lineage
    - DecisionEngine configuration
    - model inference
    - ensemble calculation
    - explainability
    - prediction persistence

PortfolioRecommendationUseCase therefore delegates every holding
to PredictUseCase.

This guarantees that:

    /recommendation/AAPL

and:

    /portfolio-recommendation

use the same ML inference architecture.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ml.decision_engine import (
    DecisionEngineResult,
)

from src.application.ml.predict_use_case import (
    PredictUseCase,
)

from src.domain.ml.exceptions import (
    InsufficientDataError,
)

from src.domain.ml.value_objects import (
    Verdict,
)


# ============================================================================
# PORTFOLIO HOLDING
# ============================================================================


@dataclass(frozen=True, slots=True)
class PortfolioHolding:
    """
    Represents one holding in the portfolio.

    Parameters
    ----------
    symbol:
        Stock ticker symbol.

    quantity:
        Number of shares/units held.
    """

    symbol: str
    quantity: float


# ============================================================================
# PORTFOLIO COMMAND
# ============================================================================


@dataclass(frozen=True, slots=True)
class PortfolioRecommendationCommand:
    """
    Input command for portfolio recommendation.
    """

    holdings: list[PortfolioHolding]

    lookback_days: int = 400


# ============================================================================
# PORTFOLIO ITEM
# ============================================================================


@dataclass(frozen=True, slots=True)
class PortfolioRecommendationItem:
    """
    Recommendation result for one portfolio holding.
    """

    symbol: str

    quantity: float

    decision: DecisionEngineResult


# ============================================================================
# PORTFOLIO RESULT
# ============================================================================


@dataclass(frozen=True, slots=True)
class PortfolioRecommendationResult:
    """
    Complete portfolio recommendation result.
    """

    items: tuple[
        PortfolioRecommendationItem,
        ...
    ]

    overall_verdict: Verdict

    overall_sentiment_score: float


# ============================================================================
# USE CASE
# ============================================================================


class PortfolioRecommendationUseCase:
    """
    Generates recommendations for all supplied portfolio holdings.

    IMPORTANT:

    This class deliberately depends on PredictUseCase rather than
    constructing DecisionEngine itself.

    PredictUseCase is the canonical ML inference pipeline.
    """

    def __init__(
        self,
        predict_use_case: PredictUseCase,
    ) -> None:

        if predict_use_case is None:

            raise ValueError(
                "PortfolioRecommendationUseCase requires "
                "a PredictUseCase."
            )

        self._predict_use_case = (
            predict_use_case
        )

    # ========================================================================
    # EXECUTE
    # ========================================================================

    async def execute(
        self,
        command: PortfolioRecommendationCommand,
    ) -> PortfolioRecommendationResult:
        """
        Generate recommendations for every portfolio holding.

        Each holding uses the same PredictUseCase pipeline as the
        normal single-symbol recommendation endpoint.
        """

        # ====================================================================
        # 1. COMMAND VALIDATION
        # ====================================================================

        if command is None:

            raise ValueError(
                "PortfolioRecommendationCommand must not be None."
            )

        if not command.holdings:

            raise InsufficientDataError(
                "PortfolioRecommendationUseCase requires "
                "at least one holding."
            )

        # ====================================================================
        # 2. LOOKBACK VALIDATION
        # ====================================================================

        if not isinstance(
            command.lookback_days,
            int,
        ):

            raise TypeError(
                "lookback_days must be an integer."
            )

        if (
            command.lookback_days < 30
            or command.lookback_days > 2000
        ):

            raise ValueError(
                "lookback_days must be between "
                "30 and 2000."
            )

        # ====================================================================
        # 3. START LOGGING
        # ====================================================================

        print(
            "=============================================================================="
        )

        print(
            "💼 PORTFOLIO RECOMMENDATION START"
        )

        print(
            f"📌 HOLDINGS: {len(command.holdings)}"
        )

        print(
            f"📌 LOOKBACK DAYS: {command.lookback_days}"
        )

        print(
            "=============================================================================="
        )

        # ====================================================================
        # 4. PROCESS HOLDINGS
        # ====================================================================

        items: list[
            PortfolioRecommendationItem
        ] = []

        skipped_symbols: list[str] = []

        for holding in command.holdings:

            # ----------------------------------------------------------------
            # NORMALIZE SYMBOL
            # ----------------------------------------------------------------

            if not isinstance(
                holding.symbol,
                str,
            ):

                raise TypeError(
                    "Portfolio holding symbol must be a string."
                )

            symbol = (
                holding.symbol
                .strip()
                .upper()
            )

            if not symbol:

                raise ValueError(
                    "Portfolio holding symbol must not be empty."
                )

            # ----------------------------------------------------------------
            # NORMALIZE QUANTITY
            # ----------------------------------------------------------------

            try:

                quantity = float(
                    holding.quantity
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ValueError(
                    f"Invalid quantity for {symbol}."
                ) from exc

            if quantity <= 0:

                raise ValueError(
                    f"Quantity for {symbol} "
                    "must be greater than zero."
                )

            # ----------------------------------------------------------------
            # HOLDING START
            # ----------------------------------------------------------------

            print(
                "----------------------------------------------------------------------"
            )

            print(
                f"💼 PROCESSING HOLDING: {symbol}"
            )

            print(
                f"📦 QUANTITY: {quantity}"
            )

            # ----------------------------------------------------------------
            # IMPORTANT
            #
            # DO NOT DO THIS:
            #
            #     DecisionEngine()
            #
            # PredictUseCase is responsible for loading the trained
            # symbol-specific models through ModelLoader.
            # ----------------------------------------------------------------

            try:

                decision = (
                    await self._predict_use_case.execute(
                        symbol=symbol,
                        news_texts=[],
                        lookback_days=command.lookback_days,
                    )
                )

            except InsufficientDataError as exc:

                print(
                    f"⚠️ SKIPPING {symbol}: "
                    f"insufficient data: {exc}"
                )

                skipped_symbols.append(
                    symbol
                )

                continue

            # ----------------------------------------------------------------
            # If a model/artifact is unavailable, the current DecisionEngine
            # may surface a ValueError. We skip that holding rather than
            # allowing one unavailable symbol to destroy the entire portfolio
            # request.
            #
            # IMPORTANT:
            #
            # Other programming errors are NOT swallowed here.
            # ----------------------------------------------------------------

            except ValueError as exc:

                error_message = str(exc)

                model_related_error = (
                    "contributing model"
                    in error_message.lower()
                    or "no models"
                    in error_message.lower()
                    or "no loaded model"
                    in error_message.lower()
                    or "model"
                    in error_message.lower()
                    and (
                        "unavailable"
                        in error_message.lower()
                        or "loaded"
                        in error_message.lower()
                    )
                )

                if not model_related_error:

                    raise

                print(
                    f"⚠️ SKIPPING {symbol}: "
                    f"model unavailable: {exc}"
                )

                skipped_symbols.append(
                    symbol
                )

                continue

            # ----------------------------------------------------------------
            # DECISION VALIDATION
            # ----------------------------------------------------------------

            if decision is None:

                raise RuntimeError(
                    f"PredictUseCase returned None "
                    f"for {symbol}."
                )

            if decision.recommendation is None:

                raise RuntimeError(
                    f"PredictUseCase returned a decision "
                    f"without a recommendation for {symbol}."
                )

            # ----------------------------------------------------------------
            # CONTRIBUTING MODEL VALIDATION
            # ----------------------------------------------------------------

            contributing_models = (
                decision.recommendation
                .contributing_models
            )

            if not contributing_models:

                print(
                    f"⚠️ SKIPPING {symbol}: "
                    "no contributing models."
                )

                skipped_symbols.append(
                    symbol
                )

                continue

            # ----------------------------------------------------------------
            # ADD RESULT
            # ----------------------------------------------------------------

            item = PortfolioRecommendationItem(
                symbol=symbol,
                quantity=quantity,
                decision=decision,
            )

            items.append(
                item
            )

            # ----------------------------------------------------------------
            # LOG RESULT
            # ----------------------------------------------------------------

            recommendation = (
                decision.recommendation
            )

            confidence = (
                recommendation.confidence.value
                if hasattr(
                    recommendation.confidence,
                    "value",
                )
                else recommendation.confidence
            )

            print(
                f"✅ {symbol} COMPLETE"
            )

            print(
                f"   VERDICT     : "
                f"{recommendation.verdict}"
            )

            print(
                f"   CONFIDENCE  : "
                f"{float(confidence):.4f}"
            )

            print(
                f"   FORECAST    : "
                f"{float(recommendation.price_forecast):.4f}"
            )

            print(
                f"   MODELS      : "
                f"{list(contributing_models)}"
            )

        # ====================================================================
        # 5. ENSURE AT LEAST ONE HOLDING SUCCEEDED
        # ====================================================================

        if not items:

            if skipped_symbols:

                raise InsufficientDataError(
                    "None of the provided portfolio holdings "
                    "could be evaluated. "
                    f"Skipped symbols: "
                    f"{', '.join(skipped_symbols)}"
                )

            raise InsufficientDataError(
                "None of the provided holdings "
                "could be evaluated."
            )

        # ====================================================================
        # 6. CALCULATE PORTFOLIO VERDICT
        # ====================================================================

        overall_verdict = _aggregate_verdict(
            items
        )

        # ====================================================================
        # 7. CALCULATE PORTFOLIO SENTIMENT
        # ====================================================================

        sentiment_values = [
            float(
                item.decision
                .recommendation
                .sentiment_score
            )
            for item in items
        ]

        overall_sentiment = (
            sum(sentiment_values)
            / len(sentiment_values)
        )

        overall_sentiment = round(
            overall_sentiment,
            4,
        )

        # ====================================================================
        # 8. BUILD RESULT
        # ====================================================================

        result = PortfolioRecommendationResult(
            items=tuple(items),
            overall_verdict=overall_verdict,
            overall_sentiment_score=overall_sentiment,
        )

        # ====================================================================
        # 9. FINAL LOGGING
        # ====================================================================

        print(
            "=============================================================================="
        )

        print(
            "🏁 PORTFOLIO RECOMMENDATION COMPLETE"
        )

        print(
            f"📌 SUCCESSFUL HOLDINGS: {len(items)}"
        )

        print(
            f"📌 SKIPPED HOLDINGS: {skipped_symbols}"
        )

        print(
            f"📌 OVERALL VERDICT: "
            f"{overall_verdict}"
        )

        print(
            f"📌 OVERALL SENTIMENT: "
            f"{overall_sentiment}"
        )

        print(
            "=============================================================================="
        )

        return result


# ============================================================================
# PORTFOLIO VERDICT AGGREGATION
# ============================================================================


def _aggregate_verdict(
    items: list[
        PortfolioRecommendationItem
    ],
) -> Verdict:
    """
    Calculate a quantity-weighted portfolio verdict.

    Example:

        AAPL -> BUY  -> quantity 10
        MSFT -> SELL -> quantity 5
        NVDA -> BUY  -> quantity 8

    BUY  = 18
    SELL = 5

    Overall = BUY
    """

    if not items:

        raise ValueError(
            "Cannot aggregate verdict from an empty portfolio."
        )

    verdict_weights: dict[
        Verdict,
        float,
    ] = {
        "buy": 0.0,
        "sell": 0.0,
        "hold": 0.0,
    }

    for item in items:

        verdict = (
            item.decision
            .recommendation
            .verdict
        )

        quantity = float(
            item.quantity
        )

        if verdict not in verdict_weights:

            raise ValueError(
                f"Unsupported verdict: {verdict!r}"
            )

        verdict_weights[
            verdict
        ] += quantity

    return max(
        verdict_weights,
        key=verdict_weights.get,
    )