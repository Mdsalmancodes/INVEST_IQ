"""Repository interfaces (Protocols) for the watchlist bounded context.

Per docs/architecture/02-clean-architecture-folder-frontend.md §4.1: these
live in the domain layer and are implemented by infrastructure — the
dependency arrow always points inward. Application-layer use cases depend
on these Protocols, never on a concrete SQLAlchemy implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.value_objects import WatchlistId

WatchlistSortField = Literal["name", "created_at", "updated_at"]
SortDirection = Literal["asc", "desc"]


@dataclass(frozen=True, slots=True)
class WatchlistListFilter:
    """Filter/pagination/sort parameters for ListWatchlists — kept as a
    plain domain-layer dataclass (not Pydantic, which belongs to the
    presentation layer), matching Portfolio's PortfolioListFilter pattern.
    """

    search: str | None = None
    """Case-insensitive substring match against the watchlist name."""
    sort_by: WatchlistSortField = "created_at"
    sort_direction: SortDirection = "desc"
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class WatchlistPageResult:
    items: tuple[Watchlist, ...]
    total_count: int
    page: int
    page_size: int


class WatchlistRepository(Protocol):
    async def save(self, watchlist: Watchlist) -> None:
        """Insert or update the Watchlist row AND persist any
        WatchlistItem rows currently attached to `watchlist.items` (upsert
        semantics, including deletions for items removed from the
        in-memory list) — the aggregate root's save() is the only write
        path, matching Portfolio's PortfolioRepository.save() convention.
        """
        ...

    async def get_by_id(self, watchlist_id: WatchlistId) -> Watchlist | None:
        """Loads the Watchlist WITH its items populated (the aggregate
        must be loaded whole, never partially, to keep add_item/
        reorder_item's invariants meaningful)."""
        ...

    async def list_for_user(
        self, user_id: str, filters: WatchlistListFilter
    ) -> WatchlistPageResult: ...

    async def delete(self, watchlist_id: WatchlistId) -> None: ...

    async def get_default_for_user(self, user_id: str) -> Watchlist | None: ...

    async def count_for_user(self, user_id: str) -> int:
        """Used by EnsureDefaultWatchlistUseCase to decide whether a user
        needs their first (default) watchlist provisioned."""
        ...
