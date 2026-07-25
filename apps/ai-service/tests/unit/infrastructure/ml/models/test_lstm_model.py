"""Unit tests for LstmModel. Uses a small synthetic price series and few
training epochs so this runs quickly in the default (non-`slow`) suite —
still a REAL torch training loop, not a mock, just deliberately small.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.infrastructure.ml.models.lstm_model import LOOKBACK_WINDOW, LstmModel


def _synthetic_prices(n: int = 100, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=0.1, scale=0.5, size=n)
    return 100 + np.cumsum(steps)


class TestHasSufficientHistory:
    def test_below_minimum_is_false(self) -> None:
        assert LstmModel.has_sufficient_history(89) is False

    def test_at_minimum_is_true(self) -> None:
        assert LstmModel.has_sufficient_history(90) is True


class TestLstmTrain:
    def test_rejects_too_little_data(self) -> None:
        model = LstmModel(hidden_size=4)
        with pytest.raises(ValueError, match="requires at least"):
            model.train(np.array([1.0, 2.0, 3.0]), epochs=1)

    def test_trains_and_returns_regression_metrics(self) -> None:
        model = LstmModel(hidden_size=4)
        prices = _synthetic_prices(100)
        result = model.train(prices, epochs=3)
        assert result.metrics.rmse >= 0
        assert result.metrics.mae >= 0
        assert result.price_std > 0


class TestLstmPredictNext:
    def test_rejects_insufficient_window(self) -> None:
        model = LstmModel(hidden_size=4)
        model.train(_synthetic_prices(100), epochs=1)
        with pytest.raises(ValueError, match="requires at least"):
            model.predict_next(np.array([1.0, 2.0]))

    def test_returns_requested_number_of_steps(self) -> None:
        model = LstmModel(hidden_size=4)
        prices = _synthetic_prices(100)
        model.train(prices, epochs=3)
        predictions = model.predict_next(prices[-LOOKBACK_WINDOW:], steps_ahead=7)
        assert len(predictions) == 7
        assert all(isinstance(p, float) for p in predictions)


class TestLstmSaveLoad:
    def test_round_trips_and_predicts_identically(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        model = LstmModel(hidden_size=4)
        prices = _synthetic_prices(100)
        model.train(prices, epochs=3)
        before = model.predict_next(prices[-LOOKBACK_WINDOW:], steps_ahead=3)

        artifact_path = tmp_path / "lstm_test.pt"
        model.save(artifact_path)
        loaded = LstmModel.load(artifact_path)
        after = loaded.predict_next(prices[-LOOKBACK_WINDOW:], steps_ahead=3)

        assert before == pytest.approx(after)
