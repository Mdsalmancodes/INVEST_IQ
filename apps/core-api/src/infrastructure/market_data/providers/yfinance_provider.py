"""YFinanceProvider — dev/local-only market data provider.

Per Document 5 §11.1: "Development/local-only provider — no API key
required, unofficial/unstable, never used in production."

This provider is the local/development Anti-Corruption Layer around
yfinance. Vendor-specific behavior and response formats stay inside this
module; the rest of the application works only with BarResult and
QuoteResult.

Float-to-Decimal conversion is performed through str() rather than
Decimal(float) to avoid importing IEEE-754 floating-point rounding error
into the domain Price value object.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import yfinance as yf

from src.application.market_data.provider import BarResult, QuoteResult
from src.domain.market_data.exceptions import NoQuoteAvailableError
from src.domain.market_data.value_objects import Interval, Price


# ========================================================================
# INTERVAL MAPPING
# ========================================================================

# Document 3 §8.1 interval values -> yfinance interval strings.
_INTERVAL_TO_YFINANCE: dict[Interval, str] = {
    Interval.ONE_MINUTE: "1m",
    Interval.FIVE_MINUTE: "5m",
    Interval.FIFTEEN_MINUTE: "15m",
    Interval.ONE_HOUR: "1h",
    Interval.ONE_DAY: "1d",
    Interval.ONE_WEEK: "1wk",
}


# ========================================================================
# PRICE CONVERSION
# ========================================================================


def _float_to_price(value: float) -> Price:
    """Convert a vendor float into the domain Price value object.

    str() is intentionally used before Decimal() so that IEEE-754 binary
    floating-point representation errors are not copied into Decimal.
    """

    return Price(Decimal(str(value)))


# ========================================================================
# PROVIDER
# ========================================================================


class YFinanceProvider:
    """Development/local yfinance implementation.

    Implements both:
        - HistoricalDataProvider
        - RealtimeQuoteProvider

    The synchronous yfinance calls are executed through asyncio.to_thread()
    so they do not block the FastAPI event loop.
    """

    # ====================================================================
    # PROVIDER NAME
    # ====================================================================

    @property
    def name(self) -> str:
        return "yfinance"

    # ====================================================================
    # REALTIME QUOTE
    # ====================================================================

    async def get_quote(
        self,
        symbol: str,
    ) -> QuoteResult:
        """Fetch the latest quote for a symbol."""

        return await asyncio.to_thread(
            self._get_quote_sync,
            symbol,
        )

    def _get_quote_sync(
        self,
        symbol: str,
    ) -> QuoteResult:
        """Synchronous implementation of get_quote()."""

        ticker = yf.Ticker(symbol)

        fast_info = ticker.fast_info

        last_price = fast_info.get("lastPrice")
        previous_close = fast_info.get("previousClose")

        if last_price is None:
            raise NoQuoteAvailableError(
                f"yfinance returned no lastPrice for symbol {symbol!r}"
            )

        return QuoteResult(
            symbol=symbol,
            price=_float_to_price(float(last_price)),
            previous_close=(
                _float_to_price(float(previous_close))
                if previous_close is not None
                else None
            ),
            as_of=datetime.now(UTC),
            source=self.name,
        )

    # ====================================================================
    # HISTORICAL BARS
    # ====================================================================

    async def get_bars(
        self,
        symbol: str,
        interval: Interval,
        start: date,
        end: date,
    ) -> tuple[BarResult, ...]:
        """Fetch historical OHLCV bars for the requested date range.

        yfinance is synchronous, therefore the blocking operation is
        executed in a worker thread.
        """

        return await asyncio.to_thread(
            self._get_bars_sync,
            symbol,
            interval,
            start,
            end,
        )

    def _get_bars_sync(
        self,
        symbol: str,
        interval: Interval,
        start: date,
        end: date,
    ) -> tuple[BarResult, ...]:
        """Synchronous historical OHLCV implementation."""

        # ----------------------------------------------------------------
        # VALIDATE DATE RANGE
        # ----------------------------------------------------------------

        if start > end:
            raise ValueError(
                f"Invalid historical date range for {symbol!r}: "
                f"start {start} is after end {end}."
            )

        # ----------------------------------------------------------------
        # RESOLVE YFINANCE INTERVAL
        # ----------------------------------------------------------------

        try:
            yf_interval = _INTERVAL_TO_YFINANCE[interval]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported interval for yfinance: {interval!r}"
            ) from exc

        # ----------------------------------------------------------------
        # CREATE TICKER
        # ----------------------------------------------------------------

        ticker = yf.Ticker(symbol)

        # ----------------------------------------------------------------
        # FETCH REQUESTED DATE RANGE
        # ----------------------------------------------------------------
        #
        # IMPORTANT:
        #
        # Do NOT use:
        #
        #     period="1mo"
        #
        # because that ignores the requested start/end dates.
        #
        # We add one day to `end` because yfinance's `end` parameter is
        # exclusive. This allows a request such as:
        #
        #     start = 2025-07-10
        #     end   = 2026-08-14
        #
        # to include data through 2026-08-13.
        #
        # This is exactly what we want for a date-based API range.
        # ----------------------------------------------------------------

        yf_start = start.isoformat()
        yf_end = (end + timedelta(days=1)).isoformat()

        df = ticker.history(
            start=yf_start,
            end=yf_end,
            interval=yf_interval,
            auto_adjust=False,
        )

        # ----------------------------------------------------------------
        # EMPTY RESPONSE
        # ----------------------------------------------------------------

        if df.empty:
            return ()

        # ----------------------------------------------------------------
        # CONVERT VENDOR DATA -> APPLICATION DTOs
        # ----------------------------------------------------------------

        results: list[BarResult] = []

        for timestamp, row in df.iterrows():

            # ------------------------------------------------------------
            # BAR TIME
            # ------------------------------------------------------------

            bar_time = timestamp.to_pydatetime()

            if bar_time.tzinfo is None:
                bar_time = bar_time.replace(tzinfo=UTC)

            # ------------------------------------------------------------
            # OHLCV
            # ------------------------------------------------------------

            try:
                open_price = float(row["Open"])
                high_price = float(row["High"])
                low_price = float(row["Low"])
                close_price = float(row["Close"])
                volume = int(row["Volume"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid OHLCV data returned by yfinance for "
                    f"{symbol!r} at {bar_time}: {exc}"
                ) from exc

            # ------------------------------------------------------------
            # BUILD APPLICATION DTO
            # ------------------------------------------------------------

            results.append(
                BarResult(
                    symbol=symbol,
                    interval=interval,
                    bar_time=bar_time,
                    open=_float_to_price(open_price),
                    high=_float_to_price(high_price),
                    low=_float_to_price(low_price),
                    close=_float_to_price(close_price),
                    volume=volume,
                    is_closed=True,
                    source=self.name,
                )
            )

        # ----------------------------------------------------------------
        # RETURN IMMUTABLE RESULT
        # ----------------------------------------------------------------

        return tuple(results)