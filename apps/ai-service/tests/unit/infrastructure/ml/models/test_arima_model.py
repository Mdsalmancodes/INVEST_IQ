"""Unit tests for ArimaModel. Uses real statsmodels ARIMA fitting on a
small synthetic price series."""

from __future__ import annotations

import numpy as np
import pytest

from src.infrastructure.ml.models.arima_model import MINIMUM_HISTORY_DAYS, ArimaModel


def _synthetic_prices(n: int = 50, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=0.05, scale=0.8, size=n)
    return 100 + np.cumsum(steps)


class TestHasSufficientHistory:
    def test_below_minimum_is_false(self) -> None:
        assert ArimaModel.has_sufficient_history(19) is False

    def test_at_minimum_is_true(self) -> None:
        assert ArimaModel.has_sufficient_history(20) is True


class TestArimaTrain:
    def test_rejects_too_little_data(self) -> None:
        model = ArimaModel()
        with pytest.raises(ValueError, match="requires at least"):
            model.train(np.array([1.0, 2.0, 3.0]))

    def test_trains_and_returns_metrics(self) -> None:
        model = ArimaModel()
        result = model.train(_synthetic_prices(50))
        assert result.metrics.rmse >= 0
        assert result.metrics.mae >= 0
        assert result.order == (5, 1, 0)

    def test_trains_with_minimal_history(self) -> None:
        model = ArimaModel()
        result = model.train(_synthetic_prices(MINIMUM_HISTORY_DAYS))
        assert result.metrics.rmse >= 0


class TestArimaPredictNext:
    def test_raises_if_not_trained(self) -> None:
        model = ArimaModel()
        with pytest.raises(RuntimeError, match="train\\(\\) must be called"):
            model.predict_next()

    def test_returns_requested_number_of_steps(self) -> None:
        model = ArimaModel()
        model.train(_synthetic_prices(50))
        predictions = model.predict_next(steps_ahead=7)
        assert len(predictions) == 7
        assert all(isinstance(p, float) for p in predictions)

    def test_supports_30_day_horizon(self) -> None:
        model = ArimaModel()
        model.train(_synthetic_prices(50))
        predictions = model.predict_next(steps_ahead=30)
        assert len(predictions) == 30


class TestArimaSaveLoad:
    def test_round_trips_and_predicts_identically(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        model = ArimaModel()
        model.train(_synthetic_prices(50))
        before = model.predict_next(steps_ahead=5)

        artifact_path = tmp_path / "arima_test.pkl"
        model.save(artifact_path)
        loaded = ArimaModel.load(artifact_path)
        after = loaded.predict_next(steps_ahead=5)

        assert before == pytest.approx(after)

    def test_save_raises_if_not_trained(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        model = ArimaModel()
        with pytest.raises(RuntimeError, match="train\\(\\) must be called"):
            model.save(tmp_path / "never_trained.pkl")
