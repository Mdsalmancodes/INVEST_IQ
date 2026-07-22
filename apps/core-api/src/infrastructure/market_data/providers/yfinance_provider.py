"""YFinanceProvider — dev/local-only market data provider.

Per Document 5 §11.1: "Development/local-only provider — no API key
required, unofficial/unstable, never used in production." This is the
ONLY provider actually exercised against live data in this phase, since
Alpha Vantage requires an API key not available in this environment (see
AlphaVantageProvider's module docstring for the disclosed limitation).

Float-to-Decimal conversion is done via `str()`, never `Decimal(float)`
directly — yfinance returns numpy float64 values, and constructing a
Decimal directly from a float imports IEEE-754 binary rounding error
(e.g. `Decimal(0.1)` is `0.1000000000000000055511151231257827021181583404541015625`,
not `0.1`); str() first gives the shortest decimal repr, matching what a
human/vendor would have actually reported.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import yfinance as yf

from src.application.market_data.provider import BarResult, QuoteResult
from src.domain.market_data.exceptions import NoQuoteAvailableError
from src.domain.market_data.value_objects import Interval, Price

# Document 3 §8.1's interval CHECK values -> yfinance's own interval strings.
_INTERVAL_TO_YFINANCE = {
    Interval.ONE_MINUTE: "1m",
    Interval.FIVE_MINUTE: "5m",
    Interval.FIFTEEN_MINUTE: "15m",
    Interval.ONE_HOUR: "1h",
    Interval.ONE_DAY: "1d",
    Interval.ONE_WEEK: "1wk",
}


def _float_to_price(value: float) -> Price:
    return Price(Decimal(str(value)))


class YFinanceProvider:
    """Implements HistoricalDataProvider and RealtimeQuoteProvider
    (together, MarketDataProvider) — see this module's docstring."""

    @property
    def name(self) -> str:
        return "yfinance"

    async def get_quote(self, symbol: str) -> QuoteResult:
        # yfinance's Ticker API is synchronous (no async support) — per
        # Document 5 §11.1, this is exactly the kind of vendor quirk the
        # Anti-Corruption Layer exists to absorb; callers of this class
        # never know or care that the underlying call blocks briefly.
        # Offloaded to a thread so it doesn't block the event loop.
        return await asyncio.to_thread(self._get_quote_sync, symbol)

    def _get_quote_sync(self, symbol: str) -> QuoteResult:
        ticker = yf.Ticker(symbol)
        fast_info = ticker.fast_info
        last_price = fast_info.get("lastPrice")
        previous_close = fast_info.get("previousClose")
        if last_price is None:
            raise NoQuoteAvailableError(f"yfinance returned no lastPrice for symbol {symbol!r}")

        return QuoteResult(
            symbol=symbol,
            price=_float_to_price(float(last_price)),
            previous_close=(
                _float_to_price(float(previous_close)) if previous_close is not None else None
            ),
            as_of=datetime.now(UTC),
            source=self.name,
        )

    async def get_bars(
        self, symbol: str, interval: Interval, start: date, end: date
    ) -> tuple[BarResult, ...]:
        return await asyncio.to_thread(self._get_bars_sync, symbol, interval, start, end)

    def _get_bars_sync(
        self, symbol: str, interval: Interval, start: date, end: date
    ) -> tuple[BarResult, ...]:
        ticker = yf.Ticker(symbol)
        yf_interval = _INTERVAL_TO_YFINANCE[interval]
        df = ticker.history(start=start, end=end, interval=yf_interval)

        if df.empty:
            return ()

        results: list[BarResult] = []
        for timestamp, row in df.iterrows():
            bar_time = timestamp.to_pydatetime()
            if bar_time.tzinfo is None:
                bar_time = bar_time.replace(tzinfo=UTC)
            results.append(
                BarResult(
                    symbol=symbol,
                    interval=interval,
                    bar_time=bar_time,
                    open=_float_to_price(float(row["Open"])),
                    high=_float_to_price(float(row["High"])),
                    low=_float_to_price(float(row["Low"])),
                    close=_float_to_price(float(row["Close"])),
                    volume=int(row["Volume"]),
                    is_closed=True,  # historical bars from `history()` are always closed
                    source=self.name,
                )
            )
        return tuple(results)
