"""Unit tests for technical indicator functions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.infrastructure.ml.features import indicators


def _price_series(n: int = 60, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=0.1, scale=1.0, size=n)
    prices = 100 + np.cumsum(steps)
    return pd.Series(prices, name="close")


def _ohlcv(n: int = 60, seed: int = 42) -> pd.DataFrame:
    close = _price_series(n, seed)
    high = close + 1.0
    low = close - 1.0
    volume = pd.Series(np.full(n, 1_000_000.0))
    return pd.DataFrame({"high": high, "low": low, "close": close, "volume": volume})


class TestSma:
    def test_early_rows_are_nan(self) -> None:
        result = indicators.sma(_price_series(30), window=10)
        assert result.iloc[:9].isna().all()

    def test_produces_a_value_once_window_reached(self) -> None:
        result = indicators.sma(_price_series(30), window=10)
        assert not pd.isna(result.iloc[9])

    def test_matches_manual_mean(self) -> None:
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = indicators.sma(series, window=3)
        assert result.iloc[2] == pytest.approx(2.0)
        assert result.iloc[4] == pytest.approx(4.0)


class TestEma:
    def test_early_rows_are_nan(self) -> None:
        result = indicators.ema(_price_series(30), window=10)
        assert result.iloc[:9].isna().all()

    def test_reacts_faster_than_sma_to_recent_change(self) -> None:
        series = pd.Series([100.0] * 20 + [200.0] * 5)
        sma_result = indicators.sma(series, window=10)
        ema_result = indicators.ema(series, window=10)
        assert ema_result.iloc[-1] > sma_result.iloc[-1]


class TestRsi:
    def test_all_gains_yields_100(self) -> None:
        series = pd.Series(list(range(1, 30)), dtype=float)
        result = indicators.rsi(series, window=14)
        assert result.iloc[-1] == pytest.approx(100.0, abs=0.01)

    def test_all_losses_yields_0(self) -> None:
        series = pd.Series(list(range(30, 1, -1)), dtype=float)
        result = indicators.rsi(series, window=14)
        assert result.iloc[-1] == pytest.approx(0.0, abs=0.01)

    def test_stays_within_bounds(self) -> None:
        result = indicators.rsi(_price_series(60), window=14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()


class TestMacd:
    def test_returns_expected_columns(self) -> None:
        result = indicators.macd(_price_series(60))
        assert set(result.columns) == {"macd_line", "macd_signal", "macd_histogram"}

    def test_histogram_equals_line_minus_signal(self) -> None:
        result = indicators.macd(_price_series(60))
        valid = result.dropna()
        diff = valid["macd_line"] - valid["macd_signal"]
        pd.testing.assert_series_equal(
            valid["macd_histogram"], diff, check_names=False, rtol=1e-9
        )


class TestBollingerBands:
    def test_upper_above_middle_above_lower(self) -> None:
        result = indicators.bollinger_bands(_price_series(60), window=20)
        valid = result.dropna()
        assert (valid["bb_upper"] >= valid["bb_middle"]).all()
        assert (valid["bb_middle"] >= valid["bb_lower"]).all()


class TestAtr:
    def test_non_negative(self) -> None:
        df = _ohlcv(60)
        result = indicators.atr(df["high"], df["low"], df["close"], window=14)
        valid = result.dropna()
        assert (valid >= 0).all()


class TestVwap:
    def test_no_leading_nan_since_no_window(self) -> None:
        df = _ohlcv(10)
        result = indicators.vwap(df["high"], df["low"], df["close"], df["volume"])
        assert not result.isna().any()

    def test_within_high_low_range_on_first_bar(self) -> None:
        df = _ohlcv(10)
        result = indicators.vwap(df["high"], df["low"], df["close"], df["volume"])
        assert df["low"].iloc[0] <= result.iloc[0] <= df["high"].iloc[0]


class TestObv:
    def test_increases_on_price_rise(self) -> None:
        close = pd.Series([100.0, 101.0, 102.0])
        volume = pd.Series([1000.0, 1000.0, 1000.0])
        result = indicators.obv(close, volume)
        assert result.iloc[1] > result.iloc[0]

    def test_decreases_on_price_fall(self) -> None:
        close = pd.Series([100.0, 99.0, 98.0])
        volume = pd.Series([1000.0, 1000.0, 1000.0])
        result = indicators.obv(close, volume)
        assert result.iloc[1] < result.iloc[0]


class TestRoc:
    def test_matches_manual_percentage_change(self) -> None:
        series = pd.Series([100.0] * 12 + [110.0])
        result = indicators.roc(series, window=12)
        assert result.iloc[-1] == pytest.approx(10.0)


class TestAdx:
    def test_stays_within_bounds(self) -> None:
        df = _ohlcv(60)
        result = indicators.adx(df["high"], df["low"], df["close"], window=14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()
