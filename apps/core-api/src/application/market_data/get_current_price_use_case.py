"""GetCurrentPriceUseCase — Document 5 §13.1's quote read path: "never
falls through to the database for the quote itself, since quotes live in
redis-cache authoritatively." Falls back to the provider chain (via
ProviderRouter) on a cache miss, then populates the cache — and falls
back further to the latest closed OHLCV bar if every live provider fails
(a stale-but-real price is better than no price at all for a dashboard).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.market_data.instrument_resolution import get_instrument_by_symbol_or_raise
from src.application.market_data.provider_router import ProviderRouter
from src.domain.market_data.exceptions import NoQuoteAvailableError
from src.domain.market_data.repositories import InstrumentRepository, OhlcvBarRepository
from src.domain.market_data.value_objects import Interval, Price
from src.infrastructure.market_data.cache import MarketDataCache


@dataclass(frozen=True, slots=True)
class CurrentPriceResult:
    symbol: str
    price: Price
    previous_close: Price | None
    source: str
    is_stale_fallback: bool  # True if served from the last closed bar, not a live quote


class GetCurrentPriceUseCase:
    def __init__(
        self,
        instrument_repository: InstrumentRepository,
        ohlcv_bar_repository: OhlcvBarRepository,
        provider_router: ProviderRouter,
        cache: MarketDataCache,
    ) -> None:
        self._instrument_repository = instrument_repository
        self._ohlcv_bar_repository = ohlcv_bar_repository
        self._provider_router = provider_router
        self._cache = cache

    async def execute(self, symbol: str) -> CurrentPriceResult:
        await get_instrument_by_symbol_or_raise(self._instrument_repository, symbol)

        cached = await self._cache.get_quote(symbol)
        if cached is not None:
            return CurrentPriceResult(
                symbol=cached.symbol,
                price=cached.price,
                previous_close=cached.previous_close,
                source=cached.source,
                is_stale_fallback=False,
            )

        try:
            quote = await self._provider_router.resolve_quote(symbol)
            await self._cache.set_quote(quote)
            return CurrentPriceResult(
                symbol=quote.symbol,
                price=quote.price,
                previous_close=quote.previous_close,
                source=quote.source,
                is_stale_fallback=False,
            )
        except Exception:  # noqa: BLE001 - deliberately broad: any provider
            # failure (including AllProvidersFailedError) falls back to the
            # last closed bar rather than propagating, since a stale-but-
            # real price beats no price for a dashboard/portfolio-value view.
            instrument = await get_instrument_by_symbol_or_raise(
                self._instrument_repository, symbol
            )
            latest_bar = await self._ohlcv_bar_repository.get_latest_closed_bar(
                instrument.id, Interval.ONE_DAY
            )
            if latest_bar is None:
                raise NoQuoteAvailableError(
                    f"No live quote or cached historical bar available for {symbol!r}"
                ) from None
            return CurrentPriceResult(
                symbol=symbol,
                price=latest_bar.close,
                previous_close=None,
                source=f"{latest_bar.source}(stale)",
                is_stale_fallback=True,
            )
