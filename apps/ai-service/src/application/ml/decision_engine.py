"""
Hybrid Decision Engine.

Combines the six required model families:

    LSTM
    ARIMA
    Prophet
    Random Forest
    XGBoost
    FinBERT

Responsibilities:

    - Execute inference only.
    - Combine model signals.
    - Produce BUY / HOLD / SELL recommendation.
    - Produce 1d / 7d / 30d price forecasts.
    - Produce Forecast domain entities for price-forecasting models.
    - Produce model-level signals.
    - Produce explainability.
    - Explicitly report excluded/unavailable models.

IMPORTANT:

Training is NOT performed inside this class.

Models must be trained offline by TrainModelUseCase and loaded
through ModelLoader before being injected into this engine.

FinBERT is pretrained and performs inference directly.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.domain.ml.entities import (
    Forecast,
    HorizonPoint,
    Recommendation,
)
from src.domain.ml.exceptions import InsufficientDataError
from src.domain.ml.value_objects import (
    Confidence,
    DataQuality,
    ExplainabilityPayload,
    FeatureContribution,
    ModelFamily,
    ModelVersionId,
    Verdict,
)

from src.infrastructure.ml.explainability.shap_explainer import (
    ShapExplainerService,
)
from src.infrastructure.ml.features.engineer import FeatureEngineer

from src.infrastructure.ml.models.arima_model import (
    MINIMUM_HISTORY_DAYS as ARIMA_MIN_DAYS,
    ArimaModel,
)
from src.infrastructure.ml.models.finbert_model import FinBertModel
from src.infrastructure.ml.models.lstm_model import (
    MINIMUM_HISTORY_DAYS as LSTM_MIN_DAYS,
    LstmModel,
)
from src.infrastructure.ml.models.prophet_model import (
    MINIMUM_HISTORY_DAYS as PROPHET_MIN_DAYS,
    ProphetModel,
)
from src.infrastructure.ml.models.random_forest_model import (
    MINIMUM_HISTORY_DAYS as RF_MIN_DAYS,
    RandomForestModel,
)
from src.infrastructure.ml.models.xgboost_model import (
    MINIMUM_HISTORY_DAYS as XGB_MIN_DAYS,
    XgboostModel,
)


# ============================================================================
# GLOBAL ENGINE REQUIREMENTS
# ============================================================================

# ARIMA / tree-based models require at least this much history.
# The DecisionEngine itself must reject obviously insufficient datasets
# instead of silently producing a fake HOLD prediction.
MINIMUM_DECISION_HISTORY_DAYS = min(
    ARIMA_MIN_DAYS,
    RF_MIN_DAYS,
    XGB_MIN_DAYS,
)


# ============================================================================
# BASE WEIGHTS
# ============================================================================

_BASE_WEIGHTS: dict[ModelFamily, float] = {
    "random_forest": 0.22,
    "xgboost": 0.22,
    "lstm": 0.20,
    "arima": 0.12,
    "prophet": 0.14,
    "finbert": 0.10,
}


_BUY_THRESHOLD = 0.15
_SELL_THRESHOLD = -0.15


# ============================================================================
# MEMBER SIGNAL
# ============================================================================


@dataclass(frozen=True, slots=True)
class MemberSignal:
    """
    Normalized contribution from one model family.

    signal:
        [-1, +1]

        -1 = strongly bearish
         0 = neutral
        +1 = strongly bullish

    confidence:
        [0, 1]

    weight:
        Normalized ensemble weight for this prediction run.
    """

    model_family: ModelFamily
    signal: float
    confidence: float
    weight: float


# ============================================================================
# ENGINE RESULT
# ============================================================================


@dataclass(frozen=True, slots=True)
class DecisionEngineResult:
    """
    Complete output of the DecisionEngine.

    member_forecasts:

        Actual Forecast domain entities produced by:

            LSTM
            ARIMA
            Prophet

    RF/XGBoost/FinBERT contribute through MemberSignal.
    """

    recommendation: Recommendation

    member_signals: tuple[MemberSignal, ...]

    member_forecasts: tuple[Forecast, ...]

    excluded_models: tuple[ModelFamily, ...]

    price_forecast_1d: float

    price_forecast_7d: float

    price_forecast_30d: float


# ============================================================================
# DECISION ENGINE
# ============================================================================


class DecisionEngine:
    """
    Six-model hybrid inference engine.

    IMPORTANT:

    Model instances supplied to this class must already be ready for
    inference.

    Training is intentionally outside this class.

    No model is fabricated when a model is unavailable.
    """

    def __init__(
        self,
        lstm: LstmModel | None = None,
        arima: ArimaModel | None = None,
        prophet: ProphetModel | None = None,
        random_forest: RandomForestModel | None = None,
        xgboost: XgboostModel | None = None,
        finbert: FinBertModel | None = None,
        model_version_ids: dict[
            ModelFamily,
            ModelVersionId,
        ]
        | None = None,
    ) -> None:

        self._lstm = lstm
        self._arima = arima
        self._prophet = prophet
        self._random_forest = random_forest
        self._xgboost = xgboost
        self._finbert = finbert

        self._model_version_ids = (
            model_version_ids or {}
        )

    # ========================================================================
    # MODEL VERSION
    # ========================================================================

    def _model_version_id(
        self,
        model_family: ModelFamily,
    ) -> ModelVersionId:

        configured = self._model_version_ids.get(
            model_family
        )

        if configured is not None:
            return configured

        namespace = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "https://invest-iq.local/runtime-model-versions",
        )

        deterministic_id = uuid.uuid5(
            namespace,
            f"invest-iq:{model_family}:runtime-v1",
        )

        return ModelVersionId(deterministic_id)

    # ========================================================================
    # MAIN DECISION
    # ========================================================================

    def decide(
        self,
        symbol: str,
        ohlcv: pd.DataFrame,
        news_texts: list[str] | None = None,
    ) -> DecisionEngineResult:

        # --------------------------------------------------------------------
        # SYMBOL
        # --------------------------------------------------------------------

        if not isinstance(symbol, str):
            raise TypeError(
                "symbol must be a string."
            )

        symbol = symbol.strip().upper()

        if not symbol:
            raise ValueError(
                "symbol cannot be empty."
            )

        # --------------------------------------------------------------------
        # BASIC INPUT VALIDATION
        # --------------------------------------------------------------------

        if not isinstance(
            ohlcv,
            pd.DataFrame,
        ):
            raise TypeError(
                "ohlcv must be a pandas DataFrame."
            )

        if ohlcv.empty:
            raise ValueError(
                "OHLCV dataframe cannot be empty."
            )

        required_columns = {
            "open",
            "high",
            "low",
            "close",
            "volume",
        }

        missing_columns = (
            required_columns
            - set(ohlcv.columns)
        )

        if missing_columns:
            raise ValueError(
                "OHLCV dataframe missing required columns: "
                f"{sorted(missing_columns)}"
            )

        ohlcv = ohlcv.copy()

        # --------------------------------------------------------------------
        # DATETIME INDEX
        # --------------------------------------------------------------------

        if not isinstance(
            ohlcv.index,
            pd.DatetimeIndex,
        ):
            try:
                ohlcv.index = pd.to_datetime(
                    ohlcv.index,
                    errors="raise",
                )
            except Exception as exc:
                raise ValueError(
                    "OHLCV index must contain valid datetime values."
                ) from exc

        if ohlcv.index.tz is not None:
            ohlcv.index = (
                ohlcv.index
                .tz_convert(None)
            )

        ohlcv = ohlcv.sort_index()

        if ohlcv.index.has_duplicates:
            raise ValueError(
                "OHLCV dataframe contains duplicate timestamps."
            )

        # --------------------------------------------------------------------
        # GLOBAL MINIMUM HISTORY
        # --------------------------------------------------------------------

        n_rows = len(ohlcv)

        if n_rows < MINIMUM_DECISION_HISTORY_DAYS:
            raise InsufficientDataError(
                "DecisionEngine requires at least "
                f"{MINIMUM_DECISION_HISTORY_DAYS} rows of OHLCV data; "
                f"received {n_rows}."
            )

        print("=" * 78)
        print("🚀 DECISION ENGINE START")
        print(f"📌 SYMBOL: {symbol}")
        print(f"📌 OHLCV ROWS: {n_rows}")
        print(
            f"📌 NEWS ITEMS: "
            f"{len(news_texts or [])}"
        )
        print("=" * 78)

        # --------------------------------------------------------------------
        # NUMERIC CLOSE
        # --------------------------------------------------------------------

        close = pd.to_numeric(
            ohlcv["close"],
            errors="coerce",
        )

        if close.isna().any():
            raise ValueError(
                f"Close price data for {symbol} "
                "contains missing or non-numeric values."
            )

        close_values = close.to_numpy(
            dtype=float
        )

        if not np.isfinite(
            close_values
        ).all():
            raise ValueError(
                f"Close price data for {symbol} "
                "contains NaN or infinite values."
            )

        if (close_values <= 0).any():
            raise ValueError(
                f"Close prices for {symbol} "
                "must be strictly positive."
            )

        current_price = float(
            close_values[-1]
        )

        if not math.isfinite(
            current_price
        ):
            raise ValueError(
                f"Current price for {symbol} is not finite."
            )

        print(
            f"💰 CURRENT PRICE: "
            f"{current_price:.4f}"
        )

        # ====================================================================
        # FEATURE ENGINEERING
        # ====================================================================

        print("⚙️ FEATURE ENGINEERING START")

        engineer = FeatureEngineer()

        feature_matrix = engineer.build(
            ohlcv
        )

        clean_features = (
            FeatureEngineer.handle_missing_values(
                feature_matrix.raw
            )
        )

        if clean_features.empty:
            raise ValueError(
                "Feature engineering produced "
                "an empty feature matrix."
            )

        last_row = clean_features.tail(1)

        print(
            "✅ FEATURE ENGINEERING COMPLETE:",
            f"shape={clean_features.shape}",
        )

        print(
            "📊 FEATURES:",
            list(clean_features.columns),
        )

        # ====================================================================
        # COLLECTIONS
        # ====================================================================

        signals: list[MemberSignal] = []

        forecasts: list[Forecast] = []

        excluded: list[ModelFamily] = []

        contributions: list[
            FeatureContribution
        ] = []

        # ====================================================================
        # DEFAULT FORECASTS
        # ====================================================================

        price_forecast_1d = current_price
        price_forecast_7d = current_price
        price_forecast_30d = current_price

        # ====================================================================
        # LSTM
        # ====================================================================

        print("=" * 78)
        print("🟢 LSTM CHECK")

        if self._lstm is None:

            print(
                "⚠️ LSTM unavailable: "
                "no loaded model"
            )

            excluded.append("lstm")

        elif not LstmModel.has_sufficient_history(
            n_rows
        ):

            print(
                "⚠️ LSTM excluded: "
                f"insufficient history "
                f"({n_rows} rows, "
                f"requires {LSTM_MIN_DAYS})"
            )

            excluded.append("lstm")

        else:

            try:

                print("🟢 LSTM START")

                # The model is already trained.
                # Only inference happens here.
                input_window = min(
                    60,
                    n_rows,
                )

                predictions = (
                    self._lstm.predict_next(
                        close_values[
                            -input_window:
                        ],
                        steps_ahead=30,
                    )
                )

                predictions = [
                    float(value)
                    for value in predictions
                ]

                if not predictions:
                    raise ValueError(
                        "LSTM returned no predictions."
                    )

                if not np.isfinite(
                    predictions
                ).all():
                    raise ValueError(
                        "LSTM returned non-finite predictions."
                    )

                price_forecast_1d = (
                    predictions[0]
                )

                price_forecast_7d = (
                    predictions[6]
                    if len(predictions) >= 7
                    else predictions[-1]
                )

                price_forecast_30d = (
                    predictions[-1]
                )

                confidence = 0.70

                signal = _direction_signal(
                    current_price,
                    price_forecast_1d,
                )

                signals.append(
                    MemberSignal(
                        model_family="lstm",
                        signal=signal,
                        confidence=confidence,
                        weight=_BASE_WEIGHTS[
                            "lstm"
                        ],
                    )
                )

                contributions.append(
                    FeatureContribution(
                        name="lstm_1d_forecast",
                        value=signal
                        * confidence,
                    )
                )

                forecasts.append(
                    _build_forecast(
                        symbol=symbol,
                        model_family="lstm",
                        predictions=predictions,
                        confidence=confidence,
                        current_price=current_price,
                        model_version_id=(
                            self._model_version_id(
                                "lstm"
                            )
                        ),
                    )
                )

                print(
                    "🟢 LSTM FINISHED:",
                    f"1d={price_forecast_1d:.4f},",
                    f"7d={price_forecast_7d:.4f},",
                    f"30d={price_forecast_30d:.4f}",
                )

            except Exception as exc:

                print(
                    "🔴 LSTM ERROR:",
                    f"{type(exc).__name__}: {exc}",
                )

                excluded.append("lstm")

        # ====================================================================
        # ARIMA
        # ====================================================================

        print("=" * 78)
        print("🟣 ARIMA CHECK")

        if self._arima is None:

            print(
                "⚠️ ARIMA unavailable: "
                "no loaded model"
            )

            excluded.append("arima")

        elif not ArimaModel.has_sufficient_history(
            n_rows
        ):

            print(
                "⚠️ ARIMA excluded: "
                f"insufficient history "
                f"({n_rows} rows, "
                f"requires {ARIMA_MIN_DAYS})"
            )

            excluded.append("arima")

        else:

            try:

                print("🟣 ARIMA START")

                predictions = (
                    self._arima.predict_next(
                        steps_ahead=30
                    )
                )

                predictions = [
                    float(value)
                    for value in predictions
                ]

                if not predictions:
                    raise ValueError(
                        "ARIMA returned no predictions."
                    )

                if not np.isfinite(
                    predictions
                ).all():
                    raise ValueError(
                        "ARIMA returned non-finite predictions."
                    )

                confidence = 0.65

                signal = _direction_signal(
                    current_price,
                    predictions[0],
                )

                signals.append(
                    MemberSignal(
                        model_family="arima",
                        signal=signal,
                        confidence=confidence,
                        weight=_BASE_WEIGHTS[
                            "arima"
                        ],
                    )
                )

                contributions.append(
                    FeatureContribution(
                        name="arima_1d_forecast",
                        value=signal
                        * confidence,
                    )
                )

                forecasts.append(
                    _build_forecast(
                        symbol=symbol,
                        model_family="arima",
                        predictions=predictions,
                        confidence=confidence,
                        current_price=current_price,
                        model_version_id=(
                            self._model_version_id(
                                "arima"
                            )
                        ),
                    )
                )

                # ARIMA becomes the forecast source only when
                # LSTM did not successfully provide one.
                if not any(
                    signal.model_family == "lstm"
                    for signal in signals
                ):

                    price_forecast_1d = (
                        predictions[0]
                    )

                    price_forecast_7d = (
                        predictions[6]
                        if len(predictions) >= 7
                        else predictions[-1]
                    )

                    price_forecast_30d = (
                        predictions[-1]
                    )

                print(
                    "🟣 ARIMA FINISHED:",
                    f"1d={predictions[0]:.4f}",
                )

            except Exception as exc:

                print(
                    "🔴 ARIMA ERROR:",
                    f"{type(exc).__name__}: {exc}",
                )

                excluded.append("arima")

        # ====================================================================
        # PROPHET
        # ====================================================================

        print("=" * 78)
        print("🔵 PROPHET CHECK")

        if self._prophet is None:

            print(
                "⚠️ Prophet unavailable: "
                "no loaded model"
            )

            excluded.append("prophet")

        elif not ProphetModel.has_sufficient_history(
            n_rows
        ):

            print(
                "⚠️ Prophet excluded: "
                f"insufficient history "
                f"({n_rows} rows, "
                f"requires {PROPHET_MIN_DAYS})"
            )

            excluded.append("prophet")

        else:

            try:

                print("🔵 PROPHET START")

                predictions = (
                    self._prophet.predict_next(
                        steps_ahead=30
                    )
                )

                predictions = [
                    float(value)
                    for value in predictions
                ]

                if not predictions:
                    raise ValueError(
                        "Prophet returned no predictions."
                    )

                if not np.isfinite(
                    predictions
                ).all():
                    raise ValueError(
                        "Prophet returned non-finite predictions."
                    )

                confidence = 0.65

                signal = _direction_signal(
                    current_price,
                    predictions[0],
                )

                signals.append(
                    MemberSignal(
                        model_family="prophet",
                        signal=signal,
                        confidence=confidence,
                        weight=_BASE_WEIGHTS[
                            "prophet"
                        ],
                    )
                )

                contributions.append(
                    FeatureContribution(
                        name="prophet_1d_forecast",
                        value=signal
                        * confidence,
                    )
                )

                forecasts.append(
                    _build_forecast(
                        symbol=symbol,
                        model_family="prophet",
                        predictions=predictions,
                        confidence=confidence,
                        current_price=current_price,
                        model_version_id=(
                            self._model_version_id(
                                "prophet"
                            )
                        ),
                    )
                )

                print(
                    "🔵 PROPHET FINISHED:",
                    f"1d={predictions[0]:.4f},",
                    "7d="
                    f"{predictions[6] if len(predictions) >= 7 else predictions[-1]:.4f},",
                    f"30d={predictions[-1]:.4f}",
                )

            except Exception as exc:

                print(
                    "🔴 PROPHET ERROR:",
                    f"{type(exc).__name__}: {exc}",
                )

                excluded.append("prophet")

        # ====================================================================
        # RANDOM FOREST
        # ====================================================================

        print("=" * 78)
        print("🟡 RANDOM FOREST CHECK")

        if self._random_forest is None:

            print(
                "⚠️ Random Forest unavailable: "
                "no loaded model"
            )

            excluded.append("random_forest")

        elif not RandomForestModel.has_sufficient_history(
            n_rows
        ):

            print(
                "⚠️ Random Forest excluded: "
                f"insufficient history "
                f"({n_rows} rows, "
                f"requires {RF_MIN_DAYS})"
            )

            excluded.append("random_forest")

        else:

            try:

                print(
                    "🟡 RANDOM FOREST START"
                )

                probability_array = (
                    self._random_forest
                    .predict_movement(
                        last_row
                    )
                )

                if len(
                    probability_array
                ) == 0:
                    raise ValueError(
                        "Random Forest returned no probability."
                    )

                probability = (
                    _clamp_probability(
                        float(
                            probability_array[
                                0
                            ]
                        )
                    )
                )

                confidence = max(
                    probability,
                    1.0 - probability,
                )

                signal = (
                    probability - 0.5
                ) * 2.0

                signals.append(
                    MemberSignal(
                        model_family="random_forest",
                        signal=signal,
                        confidence=confidence,
                        weight=_BASE_WEIGHTS[
                            "random_forest"
                        ],
                    )
                )

                contributions.extend(
                    _shap_contributions(
                        self._random_forest,
                        last_row,
                    )
                )

                print(
                    "🟡 RANDOM FOREST FINISHED:",
                    f"buy_probability={probability:.4f},",
                    f"signal={signal:+.4f}",
                )

            except Exception as exc:

                print(
                    "🔴 RANDOM FOREST ERROR:",
                    f"{type(exc).__name__}: {exc}",
                )

                excluded.append(
                    "random_forest"
                )

        # ====================================================================
        # XGBOOST
        # ====================================================================

        print("=" * 78)
        print("🔶 XGBOOST CHECK")

        if self._xgboost is None:

            print(
                "⚠️ XGBoost unavailable: "
                "no loaded model"
            )

            excluded.append("xgboost")

        elif not XgboostModel.has_sufficient_history(
            n_rows
        ):

            print(
                "⚠️ XGBoost excluded: "
                f"insufficient history "
                f"({n_rows} rows, "
                f"requires {XGB_MIN_DAYS})"
            )

            excluded.append("xgboost")

        else:

            try:

                print("🔶 XGBOOST START")

                (
                    buy_probability_array,
                    sell_probability_array,
                ) = (
                    self._xgboost
                    .predict_buy_sell_probabilities(
                        last_row
                    )
                )

                if (
                    len(
                        buy_probability_array
                    )
                    == 0
                    or len(
                        sell_probability_array
                    )
                    == 0
                ):
                    raise ValueError(
                        "XGBoost returned no probabilities."
                    )

                buy_probability = (
                    _clamp_probability(
                        float(
                            buy_probability_array[
                                0
                            ]
                        )
                    )
                )

                sell_probability = (
                    _clamp_probability(
                        float(
                            sell_probability_array[
                                0
                            ]
                        )
                    )
                )

                confidence = max(
                    buy_probability,
                    sell_probability,
                )

                # Signal is based on the BUY/SELL directional
                # probabilities rather than only buy probability.
                signal = (
                    buy_probability
                    - sell_probability
                )

                signal = float(
                    max(
                        -1.0,
                        min(
                            1.0,
                            signal,
                        ),
                    )
                )

                signals.append(
                    MemberSignal(
                        model_family="xgboost",
                        signal=signal,
                        confidence=confidence,
                        weight=_BASE_WEIGHTS[
                            "xgboost"
                        ],
                    )
                )

                contributions.extend(
                    _shap_contributions(
                        self._xgboost,
                        last_row,
                    )
                )

                print(
                    "🔶 XGBOOST FINISHED:",
                    f"buy={buy_probability:.4f},",
                    f"sell={sell_probability:.4f},",
                    f"signal={signal:+.4f}",
                )

            except Exception as exc:

                print(
                    "🔴 XGBOOST ERROR:",
                    f"{type(exc).__name__}: {exc}",
                )

                excluded.append("xgboost")

        # ====================================================================
        # FINBERT
        # ====================================================================

        print("=" * 78)
        print("🟠 FINBERT CHECK")

        sentiment_score = 0.0

        if self._finbert is None:

            print(
                "⚠️ FinBERT unavailable: "
                "no loaded model"
            )

            excluded.append("finbert")

        elif not news_texts:

            print(
                "⚠️ FinBERT excluded: "
                "no news text"
            )

            excluded.append("finbert")

        else:

            try:

                print(
                    "🟠 FINBERT START:",
                    f"{len(news_texts)} news items",
                )

                sentiment_results = (
                    self._finbert.analyze_batch(
                        news_texts
                    )
                )

                if not sentiment_results:

                    raise ValueError(
                        "FinBERT returned no sentiment results."
                    )

                label_values = {
                    "positive": 1.0,
                    "neutral": 0.0,
                    "negative": -1.0,
                }

                weighted_sentiments = []

                confidence_values = []

                for result in sentiment_results:

                    confidence = _clamp_probability(
                        float(
                            result.confidence
                        )
                    )

                    sentiment = (
                        label_values.get(
                            str(
                                result.label
                            ).lower(),
                            0.0,
                        )
                    )

                    weighted_sentiments.append(
                        sentiment
                        * confidence
                    )

                    confidence_values.append(
                        confidence
                    )

                sentiment_score = float(
                    np.mean(
                        weighted_sentiments
                    )
                )

                avg_confidence = float(
                    np.mean(
                        confidence_values
                    )
                )

                sentiment_score = max(
                    -1.0,
                    min(
                        1.0,
                        sentiment_score,
                    ),
                )

                signals.append(
                    MemberSignal(
                        model_family="finbert",
                        signal=sentiment_score,
                        confidence=avg_confidence,
                        weight=_BASE_WEIGHTS[
                            "finbert"
                        ],
                    )
                )

                contributions.append(
                    FeatureContribution(
                        name="finbert_sentiment",
                        value=sentiment_score,
                    )
                )

                print(
                    "🟠 FINBERT FINISHED:",
                    f"sentiment={sentiment_score:+.4f},",
                    f"confidence={avg_confidence:.4f}",
                )

            except Exception as exc:

                print(
                    "🔴 FINBERT ERROR:",
                    f"{type(exc).__name__}: {exc}",
                )

                excluded.append("finbert")

        # ====================================================================
        # REMOVE DUPLICATE EXCLUSIONS
        # ====================================================================

        excluded = list(
            dict.fromkeys(
                excluded
            )
        )

        # ====================================================================
        # ACTIVE MODEL SET
        # ====================================================================

        active_models = {
            signal.model_family
            for signal in signals
        }

        # A successfully executed model must never appear
        # in excluded_models.
        excluded = [
            model
            for model in excluded
            if model not in active_models
        ]

        # ====================================================================
        # NO MODEL FALLBACK
        # ====================================================================

        # IMPORTANT:
        #
        # We DO NOT create a fake LSTM/HOLD signal here.
        #
        # If all models are unavailable, the engine cannot honestly
        # claim that a model produced a prediction.
        #
        # The engine therefore produces a neutral recommendation
        # with zero contributing models.
        if not signals:

            print(
                "⚠️ NO MODELS PRODUCED SIGNALS"
            )

            weighted_signal = 0.0
            overall_confidence = 0.0
            verdict = "hold"

        else:

            # ================================================================
            # SAFE FORECASTS
            # ================================================================

            price_forecast_1d = _safe_forecast(
                price_forecast_1d,
                current_price,
            )

            price_forecast_7d = _safe_forecast(
                price_forecast_7d,
                current_price,
            )

            price_forecast_30d = _safe_forecast(
                price_forecast_30d,
                current_price,
            )

            # ================================================================
            # NORMALIZE BASE WEIGHTS
            # ================================================================

            total_weight = sum(
                signal.weight
                for signal in signals
            )

            if total_weight <= 0:
                raise RuntimeError(
                    "Active model weights must sum to a positive value."
                )

            signals = [
                MemberSignal(
                    model_family=signal.model_family,
                    signal=signal.signal,
                    confidence=signal.confidence,
                    weight=(
                        signal.weight
                        / total_weight
                    ),
                )
                for signal in signals
            ]

            # ================================================================
            # COMBINE
            # ================================================================

            (
                overall_confidence,
                weighted_signal,
            ) = _combine_signals(
                signals
            )

            verdict = _signal_to_verdict(
                weighted_signal
            )

        # ====================================================================
        # DATA QUALITY
        # ====================================================================

        data_quality = _determine_data_quality(
            n_rows=n_rows,
            excluded=excluded,
            active_models=active_models,
        )

        # ====================================================================
        # EXPLAINABILITY
        # ====================================================================

        contributions.sort(
            key=lambda contribution: abs(
                contribution.value
            ),
            reverse=True,
        )

        explainability = ExplainabilityPayload(
            top_contributions=tuple(
                contributions[:8]
            ),
            base_value=current_price,
            method=(
                "confidence_adjusted_weighted_ensemble"
            ),
            reasoning=_build_reasoning(
                verdict,
                signals,
                excluded,
            ),
        )

        # ====================================================================
        # RECOMMENDATION
        # ====================================================================

        recommendation = Recommendation.create(
            symbol=symbol,
            verdict=verdict,
            confidence=Confidence(
                round(
                    overall_confidence,
                    4,
                )
            ),
            price_forecast=price_forecast_1d,
            sentiment_score=round(
                sentiment_score,
                4,
            ),
            explainability=explainability,
            data_quality=data_quality,
            contributing_models=tuple(
                signal.model_family
                for signal in signals
            ),
        )

        # ====================================================================
        # FINAL LOGGING
        # ====================================================================

        print("=" * 78)
        print("🏁 DECISION ENGINE COMPLETE")

        print(
            f"📌 VERDICT: "
            f"{verdict.upper()}"
        )

        print(
            f"📌 CONFIDENCE: "
            f"{overall_confidence:.4f}"
        )

        print(
            f"📌 WEIGHTED SIGNAL: "
            f"{weighted_signal:+.4f}"
        )

        print(
            f"📌 1D FORECAST: "
            f"{price_forecast_1d:.4f}"
        )

        print(
            f"📌 7D FORECAST: "
            f"{price_forecast_7d:.4f}"
        )

        print(
            f"📌 30D FORECAST: "
            f"{price_forecast_30d:.4f}"
        )

        print(
            "📌 ACTIVE MODELS:",
            [
                signal.model_family
                for signal in signals
            ],
        )

        print(
            "📌 EXCLUDED MODELS:",
            excluded,
        )

        print(
            f"📌 DATA QUALITY: "
            f"{data_quality}"
        )

        print("=" * 78)

        return DecisionEngineResult(
            recommendation=recommendation,
            member_signals=tuple(
                signals
            ),
            member_forecasts=tuple(
                forecasts
            ),
            excluded_models=tuple(
                excluded
            ),
            price_forecast_1d=price_forecast_1d,
            price_forecast_7d=price_forecast_7d,
            price_forecast_30d=price_forecast_30d,
        )


# ============================================================================
# FORECAST CONSTRUCTION
# ============================================================================


def _build_forecast(
    *,
    symbol: str,
    model_family: ModelFamily,
    predictions: list[float],
    confidence: float,
    current_price: float,
    model_version_id: ModelVersionId,
) -> Forecast:

    if not predictions:
        predictions = [
            current_price
        ]

    points: list[HorizonPoint] = []

    horizons = {
        1: 0,
        7: min(
            6,
            len(predictions) - 1,
        ),
        30: min(
            29,
            len(predictions) - 1,
        ),
    }

    confidence = max(
        0.0,
        min(
            1.0,
            float(confidence),
        ),
    )

    uncertainty_fraction = max(
        0.01,
        min(
            0.25,
            0.20
            * (
                1.0
                - confidence
            ),
        ),
    )

    for (
        horizon_days,
        index,
    ) in horizons.items():

        predicted_price = float(
            predictions[index]
        )

        if not math.isfinite(
            predicted_price
        ):
            predicted_price = (
                current_price
            )

        uncertainty = (
            abs(
                predicted_price
            )
            * uncertainty_fraction
        )

        if uncertainty <= 0:
            uncertainty = max(
                abs(
                    current_price
                )
                * 0.01,
                0.01,
            )

        lower_bound = max(
            0.0,
            predicted_price
            - uncertainty,
        )

        upper_bound = (
            predicted_price
            + uncertainty
        )

        points.append(
            HorizonPoint(
                horizon_days=horizon_days,
                predicted_price=predicted_price,
                lower_bound=float(
                    lower_bound
                ),
                upper_bound=float(
                    upper_bound
                ),
            )
        )

    return Forecast.create(
        symbol=symbol,
        model_family=model_family,
        model_version_id=model_version_id,
        points=tuple(points),
        confidence=Confidence(
            round(
                confidence,
                4,
            )
        ),
        data_quality="full",
    )


# ============================================================================
# SAFE FORECAST
# ============================================================================


def _safe_forecast(
    value: float,
    fallback: float,
) -> float:

    try:
        numeric_value = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return float(
            fallback
        )

    if not math.isfinite(
        numeric_value
    ):
        return float(
            fallback
        )

    if numeric_value <= 0:
        return float(
            fallback
        )

    return numeric_value


# ============================================================================
# PROBABILITY
# ============================================================================


def _clamp_probability(
    probability: float,
) -> float:

    try:
        probability = float(
            probability
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0.5

    if not math.isfinite(
        probability
    ):
        return 0.5

    return max(
        0.0,
        min(
            1.0,
            probability,
        ),
    )


# ============================================================================
# SHAP
# ============================================================================


def _shap_contributions(
    model: object,
    feature_row: pd.DataFrame,
) -> list[FeatureContribution]:

    try:

        service = ShapExplainerService(
            model
        )

        payload = service.explain(
            feature_row
        )

        return list(
            payload.top_contributions
        )

    except Exception as exc:

        print(
            "⚠️ SHAP unavailable:",
            f"{type(exc).__name__}: {exc}",
        )

        return []


# ============================================================================
# DIRECTION SIGNAL
# ============================================================================


def _direction_signal(
    current_price: float,
    forecast_price: float,
) -> float:

    if (
        not math.isfinite(
            current_price
        )
        or not math.isfinite(
            forecast_price
        )
        or current_price <= 0
    ):
        return 0.0

    pct_change = (
        forecast_price
        - current_price
    ) / current_price

    return float(
        np.tanh(
            pct_change * 10.0
        )
    )


# ============================================================================
# SIGNAL COMBINATION
# ============================================================================


def _combine_signals(
    signals: list[MemberSignal],
) -> tuple[float, float]:

    if not signals:
        return (
            0.0,
            0.0,
        )

    confidence_adjusted_weights = [
        signal.weight
        * signal.confidence
        for signal in signals
    ]

    total_weight = sum(
        confidence_adjusted_weights
    )

    if total_weight <= 0:

        weighted_signal = float(
            np.mean(
                [
                    signal.signal
                    for signal in signals
                ]
            )
        )

        average_confidence = float(
            np.mean(
                [
                    signal.confidence
                    for signal in signals
                ]
            )
        )

        return (
            average_confidence,
            weighted_signal,
        )

    weighted_signal = (
        sum(
            signal.signal
            * adjusted_weight
            for (
                signal,
                adjusted_weight,
            ) in zip(
                signals,
                confidence_adjusted_weights,
                strict=True,
            )
        )
        / total_weight
    )

    average_confidence = float(
        np.mean(
            [
                signal.confidence
                for signal in signals
            ]
        )
    )

    signal_values = [
        signal.signal
        for signal in signals
    ]

    agreement_penalty = (
        float(
            np.std(
                signal_values
            )
        )
        if len(signal_values) > 1
        else 0.0
    )

    agreement_factor = max(
        0.2,
        1.0
        - agreement_penalty,
    )

    overall_confidence = min(
        1.0,
        max(
            0.0,
            average_confidence
            * agreement_factor,
        ),
    )

    return (
        float(
            overall_confidence
        ),
        float(
            weighted_signal
        ),
    )


# ============================================================================
# VERDICT
# ============================================================================


def _signal_to_verdict(
    weighted_signal: float,
) -> Verdict:

    if weighted_signal > _BUY_THRESHOLD:
        return "buy"

    if weighted_signal < _SELL_THRESHOLD:
        return "sell"

    return "hold"


# ============================================================================
# DATA QUALITY
# ============================================================================


def _determine_data_quality(
    *,
    n_rows: int,
    excluded: list[ModelFamily],
    active_models: set[ModelFamily],
) -> DataQuality:

    # This should normally be unreachable because decide()
    # rejects datasets below this threshold.
    if n_rows < MINIMUM_DECISION_HISTORY_DAYS:
        return "insufficientHistory"

    # All six required model families successfully participated.
    if (
        len(active_models) == 6
        and not excluded
    ):
        return "full"

    # At least one model executed, but some models were excluded.
    if active_models:
        return "partialEnsemble"

    # Sufficient market history exists, but no model was available.
    return "insufficientHistory"


# ============================================================================
# REASONING
# ============================================================================


def _build_reasoning(
    verdict: Verdict,
    signals: list[MemberSignal],
    excluded: list[ModelFamily],
) -> str:

    if signals:

        contributing = ", ".join(
            (
                f"{signal.model_family}"
                f"(signal={signal.signal:+.2f}, "
                f"confidence={signal.confidence:.2f}, "
                f"weight={signal.weight:.2f})"
            )
            for signal in signals
        )

        reasoning = (
            f"Verdict '{verdict}' derived from "
            "confidence-adjusted weighted ensemble "
            f"votes: {contributing}."
        )

    else:

        reasoning = (
            f"Verdict '{verdict}' produced because "
            "no model family successfully produced "
            "an inference signal."
        )

    if excluded:

        reasoning += (
            " Excluded model families: "
            f"{', '.join(excluded)}."
        )

    return reasoning