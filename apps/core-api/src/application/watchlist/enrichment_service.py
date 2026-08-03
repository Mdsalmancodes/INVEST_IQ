"""WatchlistEnrichmentService — the Phase 4/5 integration point.

Enriches a Watchlist's items with live price/daily change/daily %/market
status/delayed indicator/last updated, per the founder's explicit Phase 5
requirement, by calling the existing Phase 4 GetCurrentPriceUseCase (per
item) and GetMarketStatusUseCase (once per call, since market status is
global, not per-symbol) — no new market-data fetching logic is written
here; this purely orchestrates the two use cases Phase 4 already built and
maps their results onto watchlist items.

Lives in the application layer (not presentation) because it orchestrates
two other use cases — Clean Architecture's dependency rule places
orchestration logic here, with the router only doing DTO mapping.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from src.application.market_data.get_current_price_use_case import CurrentPriceResult
from src.application.market_data.get_market_status_use_case import MarketStatusResult
from src.domain.market_data.repositories import InstrumentRepository
from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.value_objects import InstrumentId


class GetCurrentPriceUseCaseProtocol(Protocol):
    """Structural type matching
    src.application.market_data.get_current_price_use_case.GetCurrentPriceUseCase
    — depending on the Protocol (not the concrete class) follows this
    codebase's established convention (e.g. PriceProvider in the portfolio
    context) of depending on abstractions, not implementations. The
    CurrentPriceResult/MarketStatusResult dataclasses themselves are
    reused directly (not re-abstracted into a further "*Like" Protocol)
    since they are already stable, framework-free application-layer DTOs
    — only the USE CASE CLASSES are abstracted here, which is what
    actually needs substituting with a fake in unit tests."""

    async def execute(self, symbol: str) -> CurrentPriceResult: ...


class GetMarketStatusUseCaseProtocol(Protocol):
    """Structural type matching
    src.application.market_data.get_market_status_use_case.GetMarketStatusUseCase.
    """

    def execute(self) -> MarketStatusResult: ...


@dataclass(frozen=True, slots=True)
class ItemQuote:
    instrument_id: InstrumentId
    symbol: str | None
    price: Decimal | None
    previous_close: Decimal | None
    daily_change: Decimal | None
    daily_change_pct: Decimal | None
    source: str | None
    is_delayed: bool
    last_updated: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class EnrichedWatchlist:
    watchlist: Watchlist
    quotes_by_item_id: dict[str, ItemQuote]
    market_status: str


class WatchlistEnrichmentService:
    def __init__(
        self,
        instrument_repository: InstrumentRepository,
        get_current_price_use_case: GetCurrentPriceUseCaseProtocol,
        get_market_status_use_case: GetMarketStatusUseCaseProtocol,
    ) -> None:
        self._instrument_repository = instrument_repository
        self._get_current_price_use_case = get_current_price_use_case
        self._get_market_status_use_case = get_market_status_use_case

    async def enrich(self, watchlist: Watchlist) -> EnrichedWatchlist:
        market_status = self._get_market_status_use_case.execute()

        # Concurrent, not sequential — Phase 5's original per-item `await`
        # in a loop meant N watchlist items cost N sequential round trips
        # (provider lookup + fallback logic per GetCurrentPriceUseCase.
        # execute()) on every GET /watchlists/{id} call. Each item's quote
        # lookup is fully independent (per-item errors are already caught
        # and reported individually inside _quote_for_item, never raised),
        # so gather() is a correctness-preserving, purely additive
        # performance fix — no change to per-item error handling/shape.
        items = watchlist.items
        quotes = await asyncio.gather(
            *(self._quote_for_item(item.instrument_id) for item in items)
        )
        quotes_by_item_id: dict[str, ItemQuote] = {
            str(item.id): quote for item, quote in zip(items, quotes, strict=True)
        }

        return EnrichedWatchlist(
            watchlist=watchlist,
            quotes_by_item_id=quotes_by_item_id,
            market_status=market_status.session,
        )

    async def _quote_for_item(self, instrument_id: InstrumentId) -> ItemQuote:
        instrument = await self._instrument_repository.get_by_id(instrument_id)
        if instrument is None:
            # The instrument was deleted/deactivated after being watchlisted
            # — genuinely possible (instruments.is_active can flip), so this
            # is reported per-item as an error, not raised, so one broken
            # item never breaks enrichment for the rest of the watchlist.
            return ItemQuote(
                instrument_id=instrument_id,
                symbol=None,
                price=None,
                previous_close=None,
                daily_change=None,
                daily_change_pct=None,
                source=None,
                is_delayed=False,
                last_updated=None,
                error="Instrument no longer exists",
            )

        try:
            result = await self._get_current_price_use_case.execute(instrument.symbol)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any
            # failure for ONE symbol (unknown to providers, network error,
            # etc.) must not break enrichment for the rest of the
            # watchlist's items — reported per-item, matching the pattern
            # GetCurrentPriceUseCase itself uses internally for provider
            # fallback.
            return ItemQuote(
                instrument_id=instrument_id,
                symbol=instrument.symbol,
                price=None,
                previous_close=None,
                daily_change=None,
                daily_change_pct=None,
                source=None,
                is_delayed=False,
                last_updated=None,
                error=str(exc),
            )

        daily_change: Decimal | None = None
        daily_change_pct: Decimal | None = None
        if result.previous_close is not None:
            daily_change = result.price.amount - result.previous_close.amount
            if result.previous_close.amount != Decimal("0"):
                daily_change_pct = (daily_change / result.previous_close.amount) * Decimal("100")

        return ItemQuote(
            instrument_id=instrument_id,
            symbol=result.symbol,
            price=result.price.amount,
            previous_close=(
                result.previous_close.amount if result.previous_close is not None else None
            ),
            daily_change=daily_change,
            daily_change_pct=daily_change_pct,
            source=result.source,
            is_delayed=result.is_stale_fallback,
            last_updated=None,
            error=None,
        )
