"""Hybrid Decision Engine — combines all 6 required model families (LSTM,
ARIMA, Prophet, Random Forest, XGBoost, FinBERT) into a single
BUY/SELL/HOLD Recommendation, per the founder's mandatory Phase 7
instruction: "The Decision Engine must combine LSTM, ARIMA, Prophet,
Random Forest, XGBoost, FinBERT using: Weighted Voting, Confidence
Scoring, Model Aggregation" and must produce "BUY/SELL/HOLD, Overall
Confidence %, Final Price Forecast, Portfolio Recommendation, Market
Sentiment Score."

Design, per Document 4 §10.1a/§10.4:
- Each model family that lacks sufficient history OR is unavailable in
  the current runtime is EXCLUDED from that specific run (not a failure)
  — the resulting Recommendation's data_quality reflects this
  ('full' | 'insufficientHistory' | 'partialEnsemble').
- Price-forecasting members (LSTM/ARIMA/Prophet) each contribute a
  directional signal (their forecast vs. current price) weighted by their
  own confidence; movement-classifier members (Random Forest/XGBoost)
  contribute an up/down probability directly; FinBERT contributes a
  sentiment signal. All six are combined via a single weighted vote,
  matching the founder's "Weighted Voting" instruction literally (not
  Document 4 §10.4's narrower rules+scoring-only synthesis, which this
  phase extends per the explicit Phase 7 instruction to also incorporate
  full ML ensemble agreement).
- Overall confidence is derived from (a) the weighted average of each
  contributing member's own confidence and (b) how strongly the members
  agree (low disagreement -> higher confidence), matching Document 4
  §10.2 step 3's "ensemble member agreement/variance" confidence formula.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.domain.ml.entities import Recommendation
from src.domain.ml.exceptions import InsufficientDataError
from src.domain.ml.value_objects import (
    Confidence,
    DataQuality,
    ExplainabilityPayload,
    FeatureContribution,
    ModelFamily,
    Verdict,
)
from src.infrastructure.ml.explainability.shap_explainer import ShapExplainerService
from src.infrastructure.ml.features.engineer import (
    FeatureEngineer,
    classification_labels_from_returns,
)
from src.infrastructure.ml.models.arima_model import MINIMUM_HISTORY_DAYS as ARIMA_MIN_DAYS
from src.infrastructure.ml.models.arima_model import ArimaModel
from src.infrastructure.ml.models.finbert_model import FinBertModel
from src.infrastructure.ml.models.lstm_model import LstmModel
from src.infrastructure.ml.models.prophet_model import ProphetModel
from src.infrastructure.ml.models.prophet_model import is_available as prophet_is_available
from src.infrastructure.ml.models.random_forest_model import (
    MINIMUM_HISTORY_DAYS as RF_MIN_DAYS,
)
from src.infrastructure.ml.models.random_forest_model import RandomForestModel
from src.infrastructure.ml.models.xgboost_model import MINIMUM_HISTORY_DAYS as XGB_MIN_DAYS
from src.infrastructure.ml.models.xgboost_model import XgboostModel

# Per the founder's "Weighted Voting" instruction: each of the 6 required
# model families gets an explicit, documented base weight, summing to 1.0.
# Tree-based classifiers (Random Forest, XGBoost) are weighted highest
# since they consume the full engineered feature set (Document 4 §10.2
# step 2's stated advantage over sequence/statistical models); LSTM is
# weighted above ARIMA/Prophet as the more expressive sequence model;
# FinBERT's sentiment signal is weighted lowest since it is a single
# contextual signal, not a price-series model.
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


@dataclass(frozen=True, slots=True)
class MemberSignal:
    """One model family's normalized contribution to the weighted vote —
    `signal` is in [-1.0, 1.0] (negative = bearish, positive = bullish),
    `weight` is that member's Document-4-§10.2-step-3-style confidence-
    adjusted vote weight for this specific run (base weight scaled by the
    member's own confidence, then renormalized across included members)."""

    model_family: ModelFamily
    signal: float
    confidence: float
    weight: float


@dataclass(frozen=True, slots=True)
class DecisionEngineResult:
    """The full output of one DecisionEngine.decide() call — the
    Recommendation entity plus the raw per-member signals, so callers
    (the presentation layer, tests) can inspect exactly how the verdict
    was reached without re-deriving it."""

    recommendation: Recommendation
    member_signals: tuple[MemberSignal, ...]
    excluded_models: tuple[ModelFamily, ...]
    price_forecast_1d: float
    price_forecast_7d: float
    price_forecast_30d: float


class DecisionEngine:
    """Orchestrates all 6 required model families for one instrument and
    combines their outputs into a single Recommendation. Model instances
    are constructor-injected (mirroring core-api's use-case-depends-on-
    repository-protocol pattern, adapted here to depend on concrete model
    wrapper instances since this phase has no separate per-model-family
    repository abstraction — ModelRegistryRepository persists trained
    artifacts, it does not inject live instances into this engine)."""

    def __init__(
        self,
        lstm: LstmModel | None = None,
        arima: ArimaModel | None = None,
        prophet: ProphetModel | None = None,
        random_forest: RandomForestModel | None = None,
        xgboost: XgboostModel | None = None,
        finbert: FinBertModel | None = None,
        feature_engineer: FeatureEngineer | None = None,
    ) -> None:
        self._lstm = lstm or LstmModel()
        self._arima = arima or ArimaModel()
        self._prophet = prophet or ProphetModel()
        self._random_forest = random_forest or RandomForestModel()
        self._xgboost = xgboost or XgboostModel()
        self._finbert = finbert or FinBertModel()
        self._feature_engineer = feature_engineer or FeatureEngineer()

    def decide(
        self,
        symbol: str,
        ohlcv: pd.DataFrame,
        news_texts: list[str] | None = None,
    ) -> DecisionEngineResult:
        """`ohlcv` must have columns [open, high, low, close, volume],
        ascending by bar_time. `news_texts` is optional recent news/social
        text for this symbol — if omitted, FinBERT is excluded from the
        vote for this run (not a failure; matches Document 4 §10.1a's
        'always available but confidence-weighted by volume' sentiment
        design applied to the degenerate zero-article case)."""
        n_rows = len(ohlcv)
        if n_rows < min(ARIMA_MIN_DAYS, RF_MIN_DAYS, XGB_MIN_DAYS):
            raise InsufficientDataError(
                f"DecisionEngine requires at least "
                f"{min(ARIMA_MIN_DAYS, RF_MIN_DAYS, XGB_MIN_DAYS)} rows of history, got {n_rows}"
            )

        close = ohlcv["close"]
        current_price = float(close.iloc[-1])
        dates = ohlcv.index.to_numpy() if not isinstance(ohlcv.index, pd.RangeIndex) else None

        signals: list[MemberSignal] = []
        excluded: list[ModelFamily] = []
        contributions: list[FeatureContribution] = []

        price_forecast_1d = current_price
        price_forecast_7d = current_price
        price_forecast_30d = current_price

        # --- LSTM ---
        if LstmModel.has_sufficient_history(n_rows):
            lstm_result = self._lstm.train(close.to_numpy())
            predictions = self._lstm.predict_next(close.to_numpy()[-60:], steps_ahead=30)
            price_forecast_1d = predictions[0]
            price_forecast_7d = predictions[6] if len(predictions) > 6 else predictions[-1]
            price_forecast_30d = predictions[-1]
            lstm_confidence = _confidence_from_rmse(lstm_result.metrics.rmse, current_price)
            lstm_signal = _direction_signal(current_price, predictions[0])
            signals.append(
                MemberSignal("lstm", lstm_signal, lstm_confidence, _BASE_WEIGHTS["lstm"])
            )
            contributions.append(
                FeatureContribution(name="lstm_1d_forecast", value=lstm_signal * lstm_confidence)
            )
        else:
            excluded.append("lstm")

        # --- ARIMA ---
        if ArimaModel.has_sufficient_history(n_rows):
            arima_result = self._arima.train(close.to_numpy())
            arima_predictions = self._arima.predict_next(steps_ahead=30)
            arima_confidence = _confidence_from_rmse(arima_result.metrics.rmse, current_price)
            arima_signal = _direction_signal(current_price, arima_predictions[0])
            signals.append(
                MemberSignal("arima", arima_signal, arima_confidence, _BASE_WEIGHTS["arima"])
            )
            contributions.append(
                FeatureContribution(
                    name="arima_1d_forecast", value=arima_signal * arima_confidence
                )
            )
            if "lstm" in excluded:
                price_forecast_1d = arima_predictions[0]
                price_forecast_7d = (
                    arima_predictions[6] if len(arima_predictions) > 6 else arima_predictions[-1]
                )
                price_forecast_30d = arima_predictions[-1]
        else:
            excluded.append("arima")

        # --- Prophet ---
        if ProphetModel.has_sufficient_history(n_rows) and prophet_is_available():
            prophet_dates = (
                dates if dates is not None else pd.date_range("2020-01-01", periods=n_rows)
            )
            prophet_result = self._prophet.train(np.asarray(prophet_dates), close.to_numpy())
            prophet_predictions = self._prophet.predict_next(steps_ahead=30)
            prophet_confidence = _confidence_from_rmse(prophet_result.metrics.rmse, current_price)
            prophet_signal = _direction_signal(current_price, prophet_predictions[0])
            signals.append(
                MemberSignal(
                    "prophet", prophet_signal, prophet_confidence, _BASE_WEIGHTS["prophet"]
                )
            )
            contributions.append(
                FeatureContribution(
                    name="prophet_1d_forecast", value=prophet_signal * prophet_confidence
                )
            )
        else:
            excluded.append("prophet")

        # --- Random Forest & XGBoost (tree-based, full feature set) ---
        feature_matrix = self._feature_engineer.build(ohlcv)
        clean_features = FeatureEngineer.handle_missing_values(feature_matrix.raw)
        labels = classification_labels_from_returns(close, horizon_days=1)
        combined = clean_features.copy()
        combined["_label"] = labels
        combined = combined.dropna()

        tree_features = combined.drop(columns=["_label"]) if len(combined) > 0 else combined
        tree_labels = combined["_label"] if len(combined) > 0 else pd.Series(dtype=float)

        if RandomForestModel.has_sufficient_history(len(combined)) and _has_both_classes(
            tree_labels
        ):
            rf_result = self._random_forest.train(tree_features, tree_labels)
            last_row = clean_features.iloc[[-1]]
            rf_probability = float(self._random_forest.predict_movement(last_row)[0])
            rf_confidence = max(rf_probability, 1.0 - rf_probability)
            rf_signal = (rf_probability - 0.5) * 2.0
            signals.append(
                MemberSignal(
                    "random_forest", rf_signal, rf_confidence, _BASE_WEIGHTS["random_forest"]
                )
            )
            contributions.extend(_shap_contributions(self._random_forest, last_row, rf_result))
        else:
            excluded.append("random_forest")

        if XgboostModel.has_sufficient_history(len(combined)) and _has_both_classes(tree_labels):
            xgb_result = self._xgboost.train(tree_features, tree_labels)
            last_row = clean_features.iloc[[-1]]
            buy_prob, _sell_prob = self._xgboost.predict_buy_sell_probabilities(last_row)
            xgb_probability = float(buy_prob[0])
            xgb_confidence = max(xgb_probability, 1.0 - xgb_probability)
            xgb_signal = (xgb_probability - 0.5) * 2.0
            signals.append(
                MemberSignal("xgboost", xgb_signal, xgb_confidence, _BASE_WEIGHTS["xgboost"])
            )
            contributions.extend(_shap_contributions(self._xgboost, last_row, xgb_result))
        else:
            excluded.append("xgboost")

        # --- FinBERT (sentiment) ---
        sentiment_score = 0.0
        if news_texts:
            sentiment_results = self._finbert.analyze_batch(news_texts)
            if sentiment_results:
                label_values = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
                weighted = sum(
                    label_values[r.label] * r.confidence for r in sentiment_results
                ) / len(sentiment_results)
                avg_confidence = sum(r.confidence for r in sentiment_results) / len(
                    sentiment_results
                )
                sentiment_score = weighted
                signals.append(
                    MemberSignal("finbert", weighted, avg_confidence, _BASE_WEIGHTS["finbert"])
                )
                contributions.append(
                    FeatureContribution(name="finbert_sentiment", value=weighted)
                )
            else:
                excluded.append("finbert")
        else:
            excluded.append("finbert")

        if not signals:
            raise InsufficientDataError(
                f"No model family could contribute a signal for {symbol!r} — "
                f"insufficient history across all 6 required models"
            )

        overall_confidence, weighted_signal = _combine_signals(signals)
        verdict = _signal_to_verdict(weighted_signal)
        data_quality = _determine_data_quality(excluded)

        contributions.sort(key=lambda c: abs(c.value), reverse=True)
        explainability = ExplainabilityPayload(
            top_contributions=tuple(contributions[:8]),
            base_value=current_price,
            method="weighted_ensemble_vote",
            reasoning=_build_reasoning(verdict, signals, excluded),
        )

        recommendation = Recommendation.create(
            symbol=symbol,
            verdict=verdict,
            confidence=Confidence(round(overall_confidence, 4)),
            price_forecast=price_forecast_1d,
            sentiment_score=round(sentiment_score, 4),
            explainability=explainability,
            data_quality=data_quality,
            contributing_models=tuple(s.model_family for s in signals),
        )

        return DecisionEngineResult(
            recommendation=recommendation,
            member_signals=tuple(signals),
            excluded_models=tuple(excluded),
            price_forecast_1d=price_forecast_1d,
            price_forecast_7d=price_forecast_7d,
            price_forecast_30d=price_forecast_30d,
        )


def _shap_contributions(
    model: object, feature_row: pd.DataFrame, train_result: object
) -> list[FeatureContribution]:
    """Real SHAP-based feature contributions for a tree-based ensemble
    member, per Document 4 §10.9 and the founder's explicit "Implement
    SHAP" instruction — replaces the simplified single-top-feature
    contribution this function's callers previously built directly from
    `feature_importances`. Falls back to that simplified single-feature
    contribution if SHAP explanation fails for any reason (e.g. an
    unsupported estimator configuration) — a real, if less detailed,
    contribution is still recorded rather than the explainability payload
    silently losing this member's input entirely."""
    try:
        service = ShapExplainerService(model)  # type: ignore[arg-type]
        payload = service.explain(feature_row)
        return list(payload.top_contributions)
    except Exception:  # noqa: BLE001 — deliberate broad fallback, see docstring
        importances: dict[str, float] = getattr(train_result, "feature_importances", {})
        if not importances:
            return []
        top_feature = max(importances.items(), key=lambda kv: kv[1])
        return [FeatureContribution(name=top_feature[0], value=top_feature[1])]


def _has_both_classes(labels: pd.Series) -> bool:
    """Guards against a genuine edge case: a strong, uninterrupted trend
    (all-up or all-down) over the training window produces a
    single-class label series, which scikit-learn/XGBoost's classifiers
    cannot fit against (they require at least 2 classes). Checks the
    actual 80% split each tree-based model's train() uses internally
    (not just the overall label set) since a single-class overall set
    with an even split could still fail the same way. Below 2 rows this
    trivially returns False rather than raising, since there is no
    meaningful split to check yet."""
    if len(labels) < 2:
        return False
    split = max(1, int(len(labels) * 0.8))
    training_slice = labels.iloc[:split]
    return bool(training_slice.nunique() >= 2)


def _direction_signal(current_price: float, forecast_price: float) -> float:
    """Converts a raw price forecast into a normalized [-1, 1] directional
    signal — magnitude capped at +/-1 via tanh so a single member with an
    extreme forecast cannot dominate the weighted vote disproportionately
    to its stated confidence."""
    if current_price == 0:
        return 0.0
    pct_change = (forecast_price - current_price) / current_price
    return float(np.tanh(pct_change * 10))


def _confidence_from_rmse(rmse: float, current_price: float) -> float:
    """Converts a regression model's RMSE into a [0, 1] confidence score
    — lower relative error (RMSE as a fraction of price) means higher
    confidence, per Document 4 §10.2 step 3's 'historical accuracy of
    this model version' confidence component, approximated here from
    the held-out validation RMSE computed during this same training call
    (no separate historical-accuracy store exists yet this phase — see
    known-issues.md)."""
    if current_price == 0:
        return 0.5
    relative_error = rmse / current_price
    return float(max(0.1, min(0.95, 1.0 - relative_error)))


def _combine_signals(signals: list[MemberSignal]) -> tuple[float, float]:
    """Returns (overall_confidence, weighted_signal). Per Document 4
    §10.2 step 3: confidence derives from (a) each member's own
    confidence weighted by its base vote weight, and (b) ensemble
    agreement (low variance across members' signals -> higher combined
    confidence, high disagreement -> lower)."""
    confidence_adjusted_weights = [s.weight * s.confidence for s in signals]
    total_weight = sum(confidence_adjusted_weights)
    if total_weight == 0:
        # All members reported zero confidence — fall back to an
        # unweighted average rather than dividing by zero.
        weighted_signal = sum(s.signal for s in signals) / len(signals)
        avg_confidence = sum(s.confidence for s in signals) / len(signals)
        return avg_confidence, weighted_signal

    weighted_signal = (
        sum(s.signal * w for s, w in zip(signals, confidence_adjusted_weights, strict=True))
        / total_weight
    )
    avg_member_confidence = sum(s.confidence for s in signals) / len(signals)

    signal_values = [s.signal for s in signals]
    agreement_penalty = float(np.std(signal_values)) if len(signal_values) > 1 else 0.0
    agreement_factor = max(0.5, 1.0 - agreement_penalty)

    overall_confidence = min(1.0, max(0.0, avg_member_confidence * agreement_factor))
    return overall_confidence, float(weighted_signal)


def _signal_to_verdict(weighted_signal: float) -> Verdict:
    if weighted_signal > _BUY_THRESHOLD:
        return "buy"
    if weighted_signal < _SELL_THRESHOLD:
        return "sell"
    return "hold"


def _determine_data_quality(excluded: list[ModelFamily]) -> DataQuality:
    if not excluded:
        return "full"
    return "partialEnsemble"


def _build_reasoning(
    verdict: Verdict, signals: list[MemberSignal], excluded: list[ModelFamily]
) -> str:
    contributing = ", ".join(f"{s.model_family} ({s.signal:+.2f})" for s in signals)
    reasoning = f"Verdict '{verdict}' derived from weighted votes: {contributing}."
    if excluded:
        reasoning += f" Excluded (insufficient history or unavailable): {', '.join(excluded)}."
    return reasoning
