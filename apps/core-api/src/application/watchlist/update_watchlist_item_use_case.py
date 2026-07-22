"""UpdateWatchlistItemUseCase — pin/unpin and/or reorder a single item.

Backs the single PATCH /watchlists/{id}/items/{itemId} endpoint (ADR-0004) —
both mutations are exposed together since they're the two "arrange my
watchlist" operations a client would naturally combine in one request
(e.g. drag-to-reorder-and-pin in one UI action), matching
UpdateWatchlistUseCase's combined rename+set-default shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.watchlist.ownership import get_owned_watchlist_or_raise
from src.domain.watchlist.entities import WatchlistItem
from src.domain.watchlist.repositories import WatchlistRepository
from src.domain.watchlist.value_objects import WatchlistId, WatchlistItemId


@dataclass(frozen=True, slots=True)
class UpdateWatchlistItemCommand:
    watchlist_id: WatchlistId
    requesting_user_id: str
    item_id: WatchlistItemId
    is_pinned: bool | None = None
    position: int | None = None


class UpdateWatchlistItemUseCase:
    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        self._watchlist_repository = watchlist_repository

    async def execute(self, command: UpdateWatchlistItemCommand) -> WatchlistItem:
        watchlist = await get_owned_watchlist_or_raise(
            self._watchlist_repository, command.watchlist_id, command.requesting_user_id
        )

        if command.is_pinned is not None:
            watchlist.set_pinned(command.item_id, command.is_pinned)
        if command.position is not None:
            watchlist.reorder_item(command.item_id, command.position)

        await self._watchlist_repository.save(watchlist)

        updated_item = next(item for item in watchlist.items if item.id == command.item_id)
        return updated_item
