"""Unit tests for HttpMarketDataRepository. Uses httpx.MockTransport to
exercise the real httpx.AsyncClient request/response/error-handling path
without requiring a live core-api server — a real HTTP client roundtrip
against a fixture response, not a mocked repository method.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from src.infrastructure.http.market_data_repository import (
    HttpMarketDataRepository,
    MarketDataUnavailableError,
)

_SAMPLE_BARS_RESPONSE = {
    "symbol": "AAPL",
    "interval": "1d",
    "bars": [
        {
            "bar_time": "2024-01-01T00:00:00+00:00",
            "open": "150.00",
            "high": "152.00",
            "low": "149.00",
            "close": "151.00",
            "adjusted_close": "151.00",
            "volume": 1_000_000,
            "is_closed": True,
            "source": "test",
        },
        {
            "bar_time": "2024-01-02T00:00:00+00:00",
            "open": "151.00",
            "high": "153.00",
            "low": "150.50",
            "close": "152.50",
            "adjusted_close": "152.50",
            "volume": 1_100_000,
            "is_closed": True,
            "source": "test",
        },
    ],
    "data_completeness": "full",
}


def _client_with_response(response: httpx.Response) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _client_with_status(status_code: int) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": "error"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestHttpMarketDataRepositoryGetOhlcvBars:
    async def test_returns_parsed_bars_on_success(self) -> None:
        response = httpx.Response(200, json=_SAMPLE_BARS_RESPONSE)
        client = _client_with_response(response)
        repo = HttpMarketDataRepository(base_url="http://core-api:8001", client=client)

        bars = await repo.get_ohlcv_bars("AAPL", date(2024, 1, 1), date(2024, 1, 2))

        assert len(bars) == 2
        assert bars[0].open == 150.00
        assert bars[0].close == 151.00
        assert bars[0].volume == 1_000_000
        assert bars[1].close == 152.50
        await client.aclose()

    async def test_raises_market_data_unavailable_on_http_error_status(self) -> None:
        client = _client_with_status(500)
        repo = HttpMarketDataRepository(base_url="http://core-api:8001", client=client)

        with pytest.raises(MarketDataUnavailableError, match="Failed to fetch"):
            await repo.get_ohlcv_bars("AAPL", date(2024, 1, 1), date(2024, 1, 2))
        await client.aclose()

    async def test_raises_market_data_unavailable_on_connection_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        repo = HttpMarketDataRepository(base_url="http://core-api:8001", client=client)

        with pytest.raises(MarketDataUnavailableError, match="Failed to fetch"):
            await repo.get_ohlcv_bars("AAPL", date(2024, 1, 1), date(2024, 1, 2))
        await client.aclose()

    async def test_strips_trailing_slash_from_base_url(self) -> None:
        captured_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_urls.append(str(request.url))
            return httpx.Response(200, json=_SAMPLE_BARS_RESPONSE)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        repo = HttpMarketDataRepository(base_url="http://core-api:8001/", client=client)

        await repo.get_ohlcv_bars("AAPL", date(2024, 1, 1), date(2024, 1, 2))

        assert captured_urls[0].startswith("http://core-api:8001/api/v1/instruments/AAPL/bars")
        await client.aclose()
