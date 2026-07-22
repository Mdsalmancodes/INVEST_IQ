"""AddWatchlistItemUseCase, RemoveWatchlistItemUseCase.

AddWatchlistItemUseCase accepts a `symbol` string (not a raw instrument_id)
and resolves it via market_data's InstrumentRepository — matching the
market_data_router.py convention of {symbol}-keyed routes for anything
user-facing (Document 4's Watchlist endpoint catalog + ADR-0004 both use
symbol-based item addition). This is Phase 5's integration point with
Phase 4's Market Data Foundation: a symbol the user types must resolve to
a real `instruments` row before it can be watchlisted.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.market_data.instrument_resolution import get_instrument_by_symbol_or_raise
from src.application.watchlist.ownership import get_owned_watchlist_or_raise
from src.domain.market_data.repositories import InstrumentRepository
from src.domain.watchlist.entities import WatchlistItem
from src.domain.watchlist.repositories import WatchlistRepository
from src.domain.watchlist.value_objects import WatchlistId, WatchlistItemId


@dataclass(frozen=True, slots=True)
class AddWatchlistItemCommand:
    watchlist_id: WatchlistId
    requesting_user_id: str
    symbol: str


class AddWatchlistItemUseCase:
    def __init__(
        self,
        watchlist_repository: WatchlistRepository,
        instrument_repository: InstrumentRepository,
    ) -> None:
        self._watchlist_repository = watchlist_repository
        self._instrument_repository = instrument_repository

    async def execute(self, command: AddWatchlistItemCommand) -> WatchlistItem:
        watchlist = await get_owned_watchlist_or_raise(
            self._watchlist_repository, command.watchlist_id, command.requesting_user_id
        )
        instrument = await get_instrument_by_symbol_or_raise(
            self._instrument_repository, command.symbol
        )
        item = watchlist.add_item(instrument.id)
        await self._watchlist_repository.save(watchlist)
        return item


@dataclass(frozen=True, slots=True)
class RemoveWatchlistItemCommand:
    watchlist_id: WatchlistId
    requesting_user_id: str
    item_id: WatchlistItemId


class RemoveWatchlistItemUseCase:
    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        self._watchlist_repository = watchlist_repository

    async def execute(self, command: RemoveWatchlistItemCommand) -> None:
        watchlist = await get_owned_watchlist_or_raise(
            self._watchlist_repository, command.watchlist_id, command.requesting_user_id
        )
        watchlist.remove_item(command.item_id)
        await self._watchlist_repository.save(watchlist)
