"""Unit tests for AlphaVantageProvider's response parsing — mocked httpx
responses using the EXACT real field-name shapes confirmed live during
development (see the module's docstring: a real curl against Alpha
Vantage's public "demo" key for GLOBAL_QUOTE/IBM returned the shape used
in test_get_quote_parses_real_response_shape below verbatim)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest

from src.domain.market_data.exceptions import AllProvidersFailedError, NoQuoteAvailableError
from src.domain.market_data.value_objects import Interval
from src.infrastructure.market_data.providers.alpha_vantage_provider import AlphaVantageProvider


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, response_json: dict[str, object], status_code: int = 200) -> None:
        self._response_json = response_json
        self._status_code = status_code

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self._status_code, json=self._response_json, request=request)


def _make_provider(
    response_json: dict[str, object], status_code: int = 200
) -> AlphaVantageProvider:
    client = httpx.AsyncClient(transport=_MockTransport(response_json, status_code))
    return AlphaVantageProvider(api_key="test-key", http_client=client)


@pytest.mark.asyncio
class TestGetQuote:
    async def test_parses_real_response_shape(self) -> None:
        # Verbatim shape from a real live request made during development
        # against Alpha Vantage's public demo key (GLOBAL_QUOTE, symbol=IBM).
        provider = _make_provider(
            {
                "Global Quote": {
                    "01. symbol": "IBM",
                    "02. open": "210.7200",
                    "03. high": "214.9700",
                    "04. low": "209.1800",
                    "05. price": "210.5000",
                    "06. volume": "11954411",
                    "07. latest trading day": "2026-07-21",
                    "08. previous close": "213.0000",
                    "09. change": "-2.5000",
                    "10. change percent": "-1.1737%",
                }
            }
        )

        result = await provider.get_quote("IBM")

        assert result.symbol == "IBM"
        assert result.price.amount == Decimal("210.50000000")
        assert result.previous_close is not None
        assert result.previous_close.amount == Decimal("213.00000000")
        assert result.source == "alpha_vantage"

    async def test_raises_when_no_quote_in_response(self) -> None:
        provider = _make_provider({"Global Quote": {}})
        with pytest.raises(NoQuoteAvailableError):
            await provider.get_quote("UNKNOWN")

    async def test_raises_on_demo_key_information_response(self) -> None:
        # The real "Information" response shape confirmed live when
        # requesting a function the demo key doesn't support.
        provider = _make_provider({"Information": "The demo API key is for demo purposes only..."})
        with pytest.raises(NoQuoteAvailableError):
            await provider.get_quote("IBM")

    async def test_raises_all_providers_failed_on_http_error(self) -> None:
        provider = _make_provider({}, status_code=500)
        with pytest.raises(AllProvidersFailedError):
            await provider.get_quote("IBM")


@pytest.mark.asyncio
class TestGetBars:
    async def test_parses_daily_series(self) -> None:
        provider = _make_provider(
            {
                "Time Series (Daily)": {
                    "2026-01-05": {
                        "1. open": "100.00",
                        "2. high": "105.00",
                        "3. low": "99.00",
                        "4. close": "103.00",
                        "5. volume": "1000000",
                    },
                    "2026-01-06": {
                        "1. open": "103.00",
                        "2. high": "108.00",
                        "3. low": "102.00",
                        "4. close": "107.00",
                        "5. volume": "1200000",
                    },
                }
            }
        )

        bars = await provider.get_bars("IBM", Interval.ONE_DAY, date(2026, 1, 1), date(2026, 1, 10))

        assert len(bars) == 2
        # sorted ascending by bar_time
        assert bars[0].bar_time.date() == date(2026, 1, 5)
        assert bars[1].bar_time.date() == date(2026, 1, 6)
        assert bars[0].close.amount == Decimal("103.00000000")
        assert bars[0].volume == 1000000

    async def test_filters_bars_outside_requested_range(self) -> None:
        provider = _make_provider(
            {
                "Time Series (Daily)": {
                    "2025-01-01": {
                        "1. open": "1",
                        "2. high": "1",
                        "3. low": "1",
                        "4. close": "1",
                        "5. volume": "1",
                    },
                    "2026-01-05": {
                        "1. open": "100.00",
                        "2. high": "105.00",
                        "3. low": "99.00",
                        "4. close": "103.00",
                        "5. volume": "1000000",
                    },
                }
            }
        )

        bars = await provider.get_bars("IBM", Interval.ONE_DAY, date(2026, 1, 1), date(2026, 1, 10))

        assert len(bars) == 1
        assert bars[0].bar_time.date() == date(2026, 1, 5)

    async def test_unsupported_interval_raises(self) -> None:
        provider = _make_provider({})
        with pytest.raises(AllProvidersFailedError):
            await provider.get_bars("IBM", Interval.ONE_MINUTE, date(2026, 1, 1), date(2026, 1, 10))

    async def test_raises_when_series_missing(self) -> None:
        provider = _make_provider({"Information": "rate limited"})
        with pytest.raises(AllProvidersFailedError):
            await provider.get_bars("IBM", Interval.ONE_DAY, date(2026, 1, 1), date(2026, 1, 10))
