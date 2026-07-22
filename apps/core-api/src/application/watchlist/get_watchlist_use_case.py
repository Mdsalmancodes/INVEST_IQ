"""GetWatchlistUseCase, ListWatchlistsUseCase — read-side use cases."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.watchlist.ownership import get_owned_watchlist_or_raise
from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.repositories import (
    SortDirection,
    WatchlistListFilter,
    WatchlistPageResult,
    WatchlistRepository,
    WatchlistSortField,
)
from src.domain.watchlist.value_objects import WatchlistId


class GetWatchlistUseCase:
    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        self._watchlist_repository = watchlist_repository

    async def execute(self, watchlist_id: WatchlistId, requesting_user_id: str) -> Watchlist:
        return await get_owned_watchlist_or_raise(
            self._watchlist_repository, watchlist_id, requesting_user_id
        )


@dataclass(frozen=True, slots=True)
class ListWatchlistsQuery:
    user_id: str
    search: str | None = None
    sort_by: WatchlistSortField = "created_at"
    sort_direction: SortDirection = "desc"
    page: int = 1
    page_size: int = 20


class ListWatchlistsUseCase:
    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        self._watchlist_repository = watchlist_repository

    async def execute(self, query: ListWatchlistsQuery) -> WatchlistPageResult:
        filters = WatchlistListFilter(
            search=query.search,
            sort_by=query.sort_by,
            sort_direction=query.sort_direction,
            page=query.page,
            page_size=query.page_size,
        )
        return await self._watchlist_repository.list_for_user(query.user_id, filters)
