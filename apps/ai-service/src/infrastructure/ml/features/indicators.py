"""Technical indicator functions — pure, stateless transformations over a
pandas DataFrame of OHLCV bars (columns: open, high, low, close, volume,
indexed by bar_time ascending).

Per Document 4 §10.1a: each indicator has an implicit minimum-window
requirement (e.g. SMA200 needs 200 rows); callers are responsible for
checking `len(df) >= window` before relying on the tail of a computed
series — early rows will be NaN by construction (not a bug, this module
never silently computes a misleading truncated-window value).

Every function takes and returns pandas Series/DataFrames only — no I/O,
no side effects, matching core-api's mapper-function purity convention
(e.g. watchlist_mappers.py) applied to numerical computation instead of
ORM translation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return close.rolling(window=window, min_periods=window).mean()


def ema(close: pd.Series, window: int) -> pd.Series:
    """Exponential Moving Average."""
    return close.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index — Wilder's smoothing method. When average
    loss is exactly zero (a pure uptrend over the window), RSI is defined
    as 100 rather than an undefined division-by-zero result — the
    standard convention, not a special-cased approximation."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()

    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
    result = 100.0 - (100.0 / (1.0 + rs))
    # avg_loss == 0 with avg_gain > 0 -> rs is +inf -> result is already 100.0.
    # avg_loss == 0 with avg_gain == 0 (flat prices) -> rs is NaN (0/0) -> RSI is neutral (50).
    result = result.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return result.astype(float)


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """Moving Average Convergence Divergence. Returns a DataFrame with
    columns `macd_line`, `macd_signal`, `macd_histogram`."""
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {"macd_line": macd_line, "macd_signal": signal_line, "macd_histogram": histogram}
    )


def bollinger_bands(
    close: pd.Series, window: int = 20, num_std: float = 2.0
) -> pd.DataFrame:
    """Bollinger Bands. Returns a DataFrame with columns `bb_middle`,
    `bb_upper`, `bb_lower`."""
    middle = sma(close, window)
    std = close.rolling(window=window, min_periods=window).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return pd.DataFrame({"bb_middle": middle, "bb_upper": upper, "bb_lower": lower})


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average True Range — Wilder's smoothing method."""
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Volume Weighted Average Price, cumulative from the start of the
    provided series (typical-price based, the standard VWAP formula)."""
    typical_price = (high + low + close) / 3.0
    cumulative_pv = (typical_price * volume).cumsum()
    cumulative_volume = volume.cumsum().replace(0, np.nan)
    return (cumulative_pv / cumulative_volume).astype(float)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    direction = close.diff().apply(lambda x: 1.0 if x > 0 else (-1.0 if x < 0 else 0.0))
    return (direction * volume).cumsum()


def roc(close: pd.Series, window: int = 12) -> pd.Series:
    """Rate of Change, expressed as a percentage."""
    shifted = close.shift(window)
    return ((close - shifted) / shifted) * 100.0


def adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average Directional Index — trend-strength indicator (Wilder)."""
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        [u if (u > d and u > 0) else 0.0 for u, d in zip(up_move, down_move, strict=True)],
        index=high.index,
    )
    minus_dm = pd.Series(
        [d if (d > u and d > 0) else 0.0 for u, d in zip(up_move, down_move, strict=True)],
        index=high.index,
    )

    true_range = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1
    ).max(axis=1)
    atr_smoothed = true_range.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()

    plus_di = 100.0 * (
        plus_dm.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean() / atr_smoothed
    )
    minus_di = 100.0 * (
        minus_dm.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean() / atr_smoothed
    )

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
