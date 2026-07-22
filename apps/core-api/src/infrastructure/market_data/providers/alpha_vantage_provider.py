"""AlphaVantageProvider — staging/production-ready provider (free-tier
delayed quotes).

Per Document 5 §11.1: "Launch (free tier): Alpha Vantage or Twelve Data
free/low tier — delayed quotes (15-20 min), strict rate limits." Built
against Alpha Vantage's REAL documented REST API shape (confirmed via a
live request against their public "demo" API key for GLOBAL_QUOTE —
`{"Global Quote": {"01. symbol": ..., "05. price": ..., "08. previous
close": ...}}`, all values as strings) — NOT guessed or hand-waved.

DISCLOSED LIMITATION: this class cannot be LIVE-TESTED end-to-end in this
environment. Alpha Vantage's `TIME_SERIES_DAILY` function (unlike
`GLOBAL_QUOTE`) rejects the public "demo" key — confirmed live via a real
request that returned `{"Information": "The demo API key is for demo
purposes only..."}` — a genuine free registered API key is required, which
is not available here. The GLOBAL_QUOTE-based get_quote() method's request/
response shape IS confirmed against a real live response; get_bars()'s
TIME_SERIES_DAILY parsing is built against Alpha Vantage's own published
documentation (numbered-key convention matching GLOBAL_QUOTE's) but not
live-exercised. See docs/phase-4/verification-report.md.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from src.application.market_data.provider import BarResult, QuoteResult
from src.domain.market_data.exceptions import AllProvidersFailedError, NoQuoteAvailableError
from src.domain.market_data.value_objects import Interval, Price

_BASE_URL = "https://www.alphavantage.co/query"

# Document 3 §8.1's interval CHECK values -> Alpha Vantage's TIME_SERIES_*
# function names (only daily+weekly map cleanly to Alpha Vantage's free-tier
# functions; intraday intervals use TIME_SERIES_INTRADAY with an
# `interval=` param instead — not exercised in this phase, not in the
# founder's explicit requirement list beyond what get_quote/get_bars need).
_INTERVAL_TO_FUNCTION = {
    Interval.ONE_DAY: "TIME_SERIES_DAILY",
    Interval.ONE_WEEK: "TIME_SERIES_WEEKLY",
}
_INTERVAL_TO_SERIES_KEY = {
    Interval.ONE_DAY: "Time Series (Daily)",
    Interval.ONE_WEEK: "Weekly Time Series",
}


class AlphaVantageProvider:
    """Implements HistoricalDataProvider and RealtimeQuoteProvider
    (together, MarketDataProvider). Requires a real API key — see module
    docstring's disclosed limitation."""

    def __init__(self, api_key: str, http_client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._http_client = http_client or httpx.AsyncClient(timeout=10.0)

    @property
    def name(self) -> str:
        return "alpha_vantage"

    async def get_quote(self, symbol: str) -> QuoteResult:
        try:
            response = await self._http_client.get(
                _BASE_URL,
                params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": self._api_key},
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise AllProvidersFailedError(
                f"Alpha Vantage request failed for symbol {symbol!r}: {exc}"
            ) from exc

        quote = body.get("Global Quote")
        if not quote or "05. price" not in quote:
            raise NoQuoteAvailableError(
                f"Alpha Vantage returned no quote for symbol {symbol!r}: {body}"
            )

        previous_close_raw = quote.get("08. previous close")
        return QuoteResult(
            symbol=symbol,
            price=Price(Decimal(quote["05. price"])),
            previous_close=(
                Price(Decimal(previous_close_raw)) if previous_close_raw is not None else None
            ),
            as_of=datetime.now(UTC),
            source=self.name,
        )

    async def get_bars(
        self, symbol: str, interval: Interval, start: date, end: date
    ) -> tuple[BarResult, ...]:
        function = _INTERVAL_TO_FUNCTION.get(interval)
        series_key = _INTERVAL_TO_SERIES_KEY.get(interval)
        if function is None or series_key is None:
            raise AllProvidersFailedError(
                f"Alpha Vantage provider does not support interval {interval.value!r} "
                "in this phase's implementation (only 1d/1w)"
            )

        try:
            response = await self._http_client.get(
                _BASE_URL,
                params={
                    "function": function,
                    "symbol": symbol,
                    "apikey": self._api_key,
                    "outputsize": "full",
                },
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise AllProvidersFailedError(
                f"Alpha Vantage request failed for symbol {symbol!r}: {exc}"
            ) from exc

        series = body.get(series_key)
        if series is None:
            raise AllProvidersFailedError(
                f"Alpha Vantage returned no {series_key!r} for symbol {symbol!r}: {body}"
            )

        results: list[BarResult] = []
        for date_str, values in series.items():
            bar_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
            if not (start <= bar_date.date() <= end):
                continue
            results.append(
                BarResult(
                    symbol=symbol,
                    interval=interval,
                    bar_time=bar_date,
                    open=Price(Decimal(values["1. open"])),
                    high=Price(Decimal(values["2. high"])),
                    low=Price(Decimal(values["3. low"])),
                    close=Price(Decimal(values["4. close"])),
                    volume=int(values["5. volume"]),
                    is_closed=True,
                    source=self.name,
                )
            )
        return tuple(sorted(results, key=lambda b: b.bar_time))
