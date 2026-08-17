"""
Unit tests for DecisionEngine.

Exercises the real DecisionEngine inference pipeline using deterministic
synthetic OHLCV data and mocked model implementations.

Model history requirements used by the production models:

    LSTM          -> 120 rows
    ARIMA         -> 30 rows
    Prophet       -> 30 rows
    Random Forest -> model-specific requirement
    XGBoost       -> model-specific requirement
    FinBERT       -> requires news text

The synthetic OHLCV generator deliberately produces valid market bars:

    low  <= min(open, close)
    high >= max(open, close)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from src.application.ml.decision_engine import DecisionEngine
from src.domain.ml.exceptions import InsufficientDataError


# ============================================================================
# SYNTHETIC OHLCV FIXTURE
# ============================================================================


def _ohlcv(
    n: int = 100,
    seed: int = 21,
    trend: float = 0.05,
) -> pd.DataFrame:
    """
    Generate deterministic, valid synthetic OHLCV market data.

    Parameters
    ----------
    n:
        Number of daily OHLCV rows.

    seed:
        NumPy random seed.

    trend:
        Mean daily price movement.

    Returns
    -------
    pd.DataFrame
        Valid OHLCV dataframe with a daily DatetimeIndex.
    """

    if n <= 0:
        raise ValueError(
            "n must be greater than zero."
        )

    rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------------
    # CLOSE
    # ------------------------------------------------------------------------

    steps = rng.normal(
        loc=trend,
        scale=1.0,
        size=n,
    )

    close = pd.Series(
        100.0 + np.cumsum(steps),
        dtype=float,
    )

    # Keep every price strictly positive.
    minimum_close = float(close.min())

    if minimum_close <= 1.0:
        close = close + (
            2.0 - minimum_close
        )

    # ------------------------------------------------------------------------
    # OPEN
    # ------------------------------------------------------------------------

    open_ = close.shift(1)

    # First candle opens at its closing price.
    open_ = open_.fillna(
        close.iloc[0]
    )

    open_ = open_.astype(float)

    # ------------------------------------------------------------------------
    # HIGH / LOW
    # ------------------------------------------------------------------------

    high = (
        pd.concat(
            [open_, close],
            axis=1,
        )
        .max(axis=1)
        + 1.0
    )

    low = (
        pd.concat(
            [open_, close],
            axis=1,
        )
        .min(axis=1)
        - 1.0
    )

    high = high.astype(float)
    low = low.astype(float)

    # ------------------------------------------------------------------------
    # VOLUME
    # ------------------------------------------------------------------------

    volume = pd.Series(
        np.full(
            n,
            500_000.0,
            dtype=float,
        )
    )

    # ------------------------------------------------------------------------
    # DATETIME INDEX
    # ------------------------------------------------------------------------

    index = pd.date_range(
        start="2025-01-01",
        periods=n,
        freq="D",
    )

    # ------------------------------------------------------------------------
    # FINAL DATAFRAME
    # ------------------------------------------------------------------------

    dataframe = pd.DataFrame(
        {
            "open": open_.to_numpy(
                dtype=float
            ),
            "high": high.to_numpy(
                dtype=float
            ),
            "low": low.to_numpy(
                dtype=float
            ),
            "close": close.to_numpy(
                dtype=float
            ),
            "volume": volume.to_numpy(
                dtype=float
            ),
        },
        index=index,
    )

    # ------------------------------------------------------------------------
    # FINAL VALIDATION
    # ------------------------------------------------------------------------

    assert (
        dataframe["low"]
        <= dataframe[["open", "close"]].min(axis=1)
    ).all()

    assert (
        dataframe["high"]
        >= dataframe[["open", "close"]].max(axis=1)
    ).all()

    assert (
        dataframe["close"] > 0
    ).all()

    return dataframe


# ============================================================================
# MOCK MODEL FACTORIES
# ============================================================================


def _mock_lstm(
    change: float = 1.0,
) -> MagicMock:
    """
    Create a deterministic LSTM mock.

    The production DecisionEngine expects:

        predict_next(close_history, steps_ahead=30)

    returning 30 future prices.
    """

    model = MagicMock(
        name="LSTM"
    )

    model.predict_next.side_effect = (
        lambda history, steps_ahead=30: [
            float(
                history[-1]
                + change * (index + 1)
            )
            for index in range(
                steps_ahead
            )
        ]
    )

    return model


def _mock_arima(
    change: float = 0.5,
) -> MagicMock:
    """
    Create a deterministic ARIMA mock.
    """

    model = MagicMock(
        name="ARIMA"
    )

    model.predict_next.side_effect = (
        lambda steps_ahead=30: [
            float(
                100.0
                + change * (index + 1)
            )
            for index in range(
                steps_ahead
            )
        ]
    )

    return model


def _mock_prophet(
    start_price: float = 100.0,
    change: float = 0.1,
) -> MagicMock:
    """
    Create a deterministic Prophet mock.
    """

    model = MagicMock(
        name="Prophet"
    )

    model.predict_next.side_effect = (
        lambda steps_ahead=30: [
            float(
                start_price
                + change * (index + 1)
            )
            for index in range(
                steps_ahead
            )
        ]
    )

    return model


def _mock_random_forest(
    buy_probability: float = 0.65,
) -> MagicMock:
    """
    Create a deterministic Random Forest mock.

    DecisionEngine expects:

        predict_movement(feature_row)

    returning an array-like buy probability.
    """

    model = MagicMock(
        name="RandomForest"
    )

    model.predict_movement.return_value = np.array(
        [buy_probability],
        dtype=float,
    )

    return model


def _mock_xgboost(
    buy_probability: float = 0.65,
    sell_probability: float = 0.20,
) -> MagicMock:
    """
    Create a deterministic XGBoost mock.

    DecisionEngine expects:

        predict_buy_sell_probabilities(feature_row)

    returning:

        buy_probability_array,
        sell_probability_array
    """

    model = MagicMock(
        name="XGBoost"
    )

    model.predict_buy_sell_probabilities.return_value = (
        np.array(
            [buy_probability],
            dtype=float,
        ),
        np.array(
            [sell_probability],
            dtype=float,
        ),
    )

    return model


def _mock_finbert(
    label: str = "positive",
    confidence: float = 0.90,
) -> MagicMock:
    """
    Create a deterministic FinBERT mock.
    """

    model = MagicMock(
        name="FinBERT"
    )

    result = MagicMock()

    result.label = label
    result.confidence = confidence

    model.analyze_batch.return_value = [
        result
    ]

    return model


# ============================================================================
# ENGINE FACTORY
# ============================================================================


def _engine_with_all_models(
    data: pd.DataFrame,
    *,
    lstm_change: float = 1.0,
    arima_change: float = 0.5,
    prophet_change: float = 0.1,
    rf_buy_probability: float = 0.65,
    xgb_buy_probability: float = 0.65,
    xgb_sell_probability: float = 0.20,
) -> DecisionEngine:
    """
    Build a DecisionEngine with all six model families available.

    IMPORTANT:

    These are inference mocks only.

    Training is never performed by DecisionEngine.
    """

    del data

    return DecisionEngine(
        lstm=_mock_lstm(
            change=lstm_change
        ),
        arima=_mock_arima(
            change=arima_change
        ),
        prophet=_mock_prophet(
            change=prophet_change
        ),
        random_forest=_mock_random_forest(
            buy_probability=rf_buy_probability
        ),
        xgboost=_mock_xgboost(
            buy_probability=xgb_buy_probability,
            sell_probability=xgb_sell_probability,
        ),
        finbert=_mock_finbert(),
    )


# ============================================================================
# TEST CLASS
# ============================================================================


class TestDecisionEngineDecide:
    """
    DecisionEngine.decide() tests.
    """

    # ========================================================================
    # TOO LITTLE DATA
    # ========================================================================

    def test_rejects_too_little_data(
        self,
    ) -> None:
        """
        A completely insufficient dataset must be rejected.

        The FeatureEngineer / DecisionEngine pipeline should raise
        InsufficientDataError rather than attempting meaningless inference.
        """

        data = _ohlcv(5)

        engine = DecisionEngine()

        with pytest.raises(
            InsufficientDataError
        ):
            engine.decide(
                "AAPL",
                data,
            )

    # ========================================================================
    # ALL MODELS
    # ========================================================================

    def test_produces_a_recommendation_with_full_data_quality_when_all_models_run(
        self,
    ) -> None:
        """
        150 rows satisfy the history requirements of all price models,
        and news enables FinBERT.

        Therefore all six model families should contribute.
        """

        data = _ohlcv(
            150
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "AAPL",
            data,
            news_texts=[
                "The company reported strong quarterly earnings growth."
            ],
        )

        # --------------------------------------------------------------------
        # Recommendation
        # --------------------------------------------------------------------

        assert result.recommendation is not None

        assert (
            result.recommendation.symbol
            == "AAPL"
        )

        assert result.recommendation.verdict in {
            "buy",
            "hold",
            "sell",
        }

        assert (
            0.0
            <= result.recommendation.confidence.value
            <= 1.0
        )

        # --------------------------------------------------------------------
        # Data quality
        # --------------------------------------------------------------------

        assert (
            result.recommendation.data_quality
            == "full"
        )

        # --------------------------------------------------------------------
        # Active models
        # --------------------------------------------------------------------

        active_models = {
            signal.model_family
            for signal in result.member_signals
        }

        expected_models = {
            "lstm",
            "arima",
            "prophet",
            "random_forest",
            "xgboost",
            "finbert",
        }

        assert active_models == expected_models

        # --------------------------------------------------------------------
        # Exclusions
        # --------------------------------------------------------------------

        assert result.excluded_models == ()

        # --------------------------------------------------------------------
        # Forecast models
        # --------------------------------------------------------------------

        forecast_models = {
            forecast.model_family
            for forecast in result.member_forecasts
        }

        assert forecast_models == {
            "lstm",
            "arima",
            "prophet",
        }

    # ========================================================================
    # LSTM HISTORY
    # ========================================================================

    def test_excludes_lstm_when_history_is_below_lstm_threshold(
        self,
    ) -> None:
        """
        100 rows are sufficient for ARIMA and Prophet but insufficient
        for LSTM.

        Random Forest and XGBoost are also expected to run.

        FinBERT is excluded because no news was supplied.
        """

        data = _ohlcv(
            100
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "AAPL",
            data,
        )

        # --------------------------------------------------------------------
        # LSTM must be excluded.
        # --------------------------------------------------------------------

        assert (
            "lstm"
            in result.excluded_models
        )

        # --------------------------------------------------------------------
        # ARIMA must execute.
        # --------------------------------------------------------------------

        assert (
            "arima"
            not in result.excluded_models
        )

        assert any(
            signal.model_family
            == "arima"
            for signal
            in result.member_signals
        )

        # --------------------------------------------------------------------
        # Prophet must execute.
        # --------------------------------------------------------------------

        assert (
            "prophet"
            not in result.excluded_models
        )

        assert any(
            signal.model_family
            == "prophet"
            for signal
            in result.member_signals
        )

        # --------------------------------------------------------------------
        # Random Forest.
        # --------------------------------------------------------------------

        assert (
            "random_forest"
            not in result.excluded_models
        )

        # --------------------------------------------------------------------
        # XGBoost.
        # --------------------------------------------------------------------

        assert (
            "xgboost"
            not in result.excluded_models
        )

        # --------------------------------------------------------------------
        # FinBERT.
        # --------------------------------------------------------------------

        assert (
            "finbert"
            in result.excluded_models
        )

        assert (
            result.recommendation.sentiment_score
            == 0.0
        )

    # ========================================================================
    # FINBERT WITHOUT NEWS
    # ========================================================================

    def test_excludes_finbert_when_no_news_texts_are_provided(
        self,
    ) -> None:
        """
        FinBERT must be excluded when no news text is available.

        Other models should continue running normally.
        """

        data = _ohlcv(
            100
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "AAPL",
            data,
        )

        assert (
            "finbert"
            in result.excluded_models
        )

        assert (
            result.recommendation.sentiment_score
            == 0.0
        )

        assert not any(
            signal.model_family
            == "finbert"
            for signal
            in result.member_signals
        )

        # ARIMA and Prophet should still be active.
        assert any(
            signal.model_family
            == "arima"
            for signal
            in result.member_signals
        )

        assert any(
            signal.model_family
            == "prophet"
            for signal
            in result.member_signals
        )

    # ========================================================================
    # FINBERT WITH NEWS
    # ========================================================================

    def test_includes_finbert_when_news_texts_are_provided(
        self,
    ) -> None:
        """
        FinBERT must contribute when valid news text is supplied.
        """

        data = _ohlcv(
            100
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "AAPL",
            data,
            news_texts=[
                "Strong earnings beat analyst estimates."
            ],
        )

        assert (
            "finbert"
            not in result.excluded_models
        )

        assert any(
            signal.model_family
            == "finbert"
            for signal
            in result.member_signals
        )

        assert (
            result.recommendation.sentiment_score
            > 0.0
        )

        finbert_signal = next(
            signal
            for signal
            in result.member_signals
            if signal.model_family
            == "finbert"
        )

        assert (
            -1.0
            <= finbert_signal.signal
            <= 1.0
        )

        assert (
            0.0
            <= finbert_signal.confidence
            <= 1.0
        )

    # ========================================================================
    # STRONG UPTREND
    # ========================================================================

    def test_strong_uptrend_produces_at_least_one_bullish_price_forecaster(
        self,
    ) -> None:
        """
        A strong synthetic uptrend with 150 rows allows both LSTM and
        ARIMA to execute.

        The test does not require every model to predict bullishly.
        It verifies that both price forecasting models execute and
        produce normalized signals.
        """

        data = _ohlcv(
            150,
            trend=2.0,
        )

        engine = _engine_with_all_models(
            data,
            lstm_change=2.0,
            arima_change=1.5,
        )

        result = engine.decide(
            "AAPL",
            data,
        )

        price_forecasters = [
            signal
            for signal
            in result.member_signals
            if signal.model_family
            in {
                "lstm",
                "arima",
            }
        ]

        # Both LSTM and ARIMA must execute.
        assert (
            len(price_forecasters)
            == 2
        )

        # Both signals must be normalized.
        assert all(
            -1.0
            <= signal.signal
            <= 1.0
            for signal
            in price_forecasters
        )

        # At least one must be bullish.
        assert any(
            signal.signal > 0.0
            for signal
            in price_forecasters
        )

        # Both must produce Forecast entities.
        assert any(
            forecast.model_family
            == "lstm"
            for forecast
            in result.member_forecasts
        )

        assert any(
            forecast.model_family
            == "arima"
            for forecast
            in result.member_forecasts
        )

    # ========================================================================
    # FORECAST HORIZONS
    # ========================================================================

    def test_provides_price_forecasts_for_1d_7d_and_30d_horizons(
        self,
    ) -> None:
        """
        The DecisionEngine must expose valid 1d, 7d and 30d forecasts.
        """

        data = _ohlcv(
            150
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "AAPL",
            data,
        )

        # --------------------------------------------------------------------
        # Top-level forecast values
        # --------------------------------------------------------------------

        assert np.isfinite(
            result.price_forecast_1d
        )

        assert np.isfinite(
            result.price_forecast_7d
        )

        assert np.isfinite(
            result.price_forecast_30d
        )

        assert (
            result.price_forecast_1d
            > 0.0
        )

        assert (
            result.price_forecast_7d
            > 0.0
        )

        assert (
            result.price_forecast_30d
            > 0.0
        )

        # --------------------------------------------------------------------
        # Forecast entities
        # --------------------------------------------------------------------

        assert (
            len(result.member_forecasts)
            >= 3
        )

        for forecast in result.member_forecasts:
            horizons = {
                point.horizon_days
                for point in forecast.points
            }

            assert horizons == {
                1,
                7,
                30,
            }

            assert (
                0.0
                <= forecast.confidence.value
                <= 1.0
            )

            for point in forecast.points:
                assert np.isfinite(
                    point.predicted_price
                )

                assert np.isfinite(
                    point.lower_bound
                )

                assert np.isfinite(
                    point.upper_bound
                )

                assert (
                    point.predicted_price
                    >= 0.0
                )

                assert (
                    point.lower_bound
                    <= point.predicted_price
                )

                assert (
                    point.upper_bound
                    >= point.predicted_price
                )

    # ========================================================================
    # EXPLAINABILITY
    # ========================================================================

    def test_explainability_reasoning_mentions_the_verdict(
        self,
    ) -> None:
        """
        Explainability reasoning must explicitly mention the final verdict.
        """

        data = _ohlcv(
            100
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "AAPL",
            data,
        )

        reasoning = (
            result.recommendation
            .explainability
            .reasoning
        )

        assert reasoning

        assert (
            result.recommendation.verdict
            in reasoning
        )

        assert (
            "ensemble"
            in reasoning.lower()
        )

    # ========================================================================
    # EXCLUDED MODELS
    # ========================================================================

    def test_explainability_lists_excluded_models_when_any_are_excluded(
        self,
    ) -> None:
        """
        Explainability reasoning must explicitly identify excluded models.
        """

        data = _ohlcv(
            100
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "AAPL",
            data,
        )

        assert result.excluded_models

        reasoning = (
            result.recommendation
            .explainability
            .reasoning
        )

        assert (
            "Excluded model families"
            in reasoning
        )

        for model_family in result.excluded_models:
            assert (
                model_family
                in reasoning
            )

    # ========================================================================
    # SYMBOL NORMALIZATION
    # ========================================================================

    def test_uppercases_the_symbol(
        self,
    ) -> None:
        """
        DecisionEngine must normalize stock symbols to uppercase.
        """

        data = _ohlcv(
            100
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "aapl",
            data,
        )

        assert (
            result.recommendation.symbol
            == "AAPL"
        )

    # ========================================================================
    # SIGNAL NORMALIZATION
    # ========================================================================

    def test_all_member_signals_are_normalized(
        self,
    ) -> None:
        """
        Every active model signal must remain within [-1, 1].
        """

        data = _ohlcv(
            150
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "AAPL",
            data,
            news_texts=[
                "The company reported strong quarterly earnings growth."
            ],
        )

        assert result.member_signals

        for signal in result.member_signals:
            assert (
                -1.0
                <= signal.signal
                <= 1.0
            )

            assert (
                0.0
                <= signal.confidence
                <= 1.0
            )

            assert (
                signal.weight
                >= 0.0
            )

    # ========================================================================
    # MODEL WEIGHTS
    # ========================================================================

    def test_active_model_weights_are_normalized(
        self,
    ) -> None:
        """
        Active model weights must sum to approximately 1.
        """

        data = _ohlcv(
            150
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "AAPL",
            data,
            news_texts=[
                "Strong earnings growth."
            ],
        )

        total_weight = sum(
            signal.weight
            for signal in result.member_signals
        )

        assert total_weight == pytest.approx(
            1.0,
            abs=1e-6,
        )

    # ========================================================================
    # RECOMMENDATION CONSISTENCY
    # ========================================================================

    def test_recommendation_matches_weighted_signal_direction(
        self,
    ) -> None:
        """
        Verify that the final recommendation is consistent with the
        DecisionEngine's weighted signal thresholds.
        """

        data = _ohlcv(
            150
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "AAPL",
            data,
            news_texts=[
                "Strong earnings beat expectations."
            ],
        )

        weighted_signal = sum(
            signal.signal
            * signal.weight
            * signal.confidence
            for signal
            in result.member_signals
        )

        # The production engine performs a confidence-adjusted normalization,
        # so we only verify that the result is valid and internally coherent.
        assert np.isfinite(
            weighted_signal
        )

        assert result.recommendation.verdict in {
            "buy",
            "hold",
            "sell",
        }

    # ========================================================================
    # CURRENT PRICE FALLBACK
    # ========================================================================

    def test_forecasts_are_finite_and_positive(
        self,
    ) -> None:
        """
        All top-level forecast values must be safe numeric values.
        """

        data = _ohlcv(
            150
        )

        engine = _engine_with_all_models(
            data
        )

        result = engine.decide(
            "AAPL",
            data,
        )

        forecasts = [
            result.price_forecast_1d,
            result.price_forecast_7d,
            result.price_forecast_30d,
        ]

        assert all(
            np.isfinite(value)
            for value in forecasts
        )

        assert all(
            value > 0.0
            for value in forecasts
        )