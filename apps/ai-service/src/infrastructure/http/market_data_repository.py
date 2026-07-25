"""HttpMarketDataRepository — implements
src.domain.ml.repositories.MarketDataRepository by calling core-api's
existing public GET /api/v1/instruments/{symbol}/bars endpoint.

Per the founder's Phase 7 instruction: "Reuse the existing Market Data
module. Reuse existing OHLCV tables... Never duplicate data." This
repository is the ONLY way ai-service reads OHLCV history — it never
opens its own Postgres connection or reimplements the ohlcv_bars schema,
matching core-api's market_data_router.py's documented public/
unauthenticated design for these specific endpoints (no bearer token is
sent or required).
"""

from __future__ import annotations

from datetime import date, datetime

import httpx

from src.domain.ml.exceptions import MlDomainError
from src.domain.ml.repositories import OhlcvBar


class MarketDataUnavailableError(MlDomainError):
    """Raised when core-api's market-data endpoint cannot be reached or
    returns an error — distinct from InsufficientDataError (which means
    the data exists but is too short), this means the data could not be
    fetched at all."""


class HttpMarketDataRepository:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def get_ohlcv_bars(
        self, symbol: str, start: date, end: date, interval: str = "1d"
    ) -> tuple[OhlcvBar, ...]:
        params = {
            "interval": interval,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        url = f"{self._base_url}/api/v1/instruments/{symbol}/bars"

        try:
            if self._client is not None:
                response = await self._client.get(url, params=params)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataUnavailableError(
                f"Failed to fetch OHLCV bars for {symbol!r} from core-api: {exc}"
            ) from exc

        payload = response.json()
        bars = tuple(
            OhlcvBar(
                bar_time=datetime.fromisoformat(bar["bar_time"]),
                open=float(bar["open"]),
                high=float(bar["high"]),
                low=float(bar["low"]),
                close=float(bar["close"]),
                adjusted_close=float(bar["adjusted_close"]),
                volume=int(bar["volume"]),
            )
            for bar in payload["bars"]
        )
        return bars
