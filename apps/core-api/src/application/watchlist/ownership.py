"""Shared ownership-enforcement helper for watchlist use cases.

Document 3 §7.5's resource-level ownership rule, applied consistently
across every use case that operates on a specific watchlist_id — mirrors
src.application.portfolio.ownership's role for the portfolio context.
"""

from __future__ import annotations

from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.exceptions import WatchlistNotFoundError, WatchlistOwnershipError
from src.domain.watchlist.repositories import WatchlistRepository
from src.domain.watchlist.value_objects import WatchlistId


async def get_owned_watchlist_or_raise(
    watchlist_repository: WatchlistRepository, watchlist_id: WatchlistId, requesting_user_id: str
) -> Watchlist:
    watchlist = await watchlist_repository.get_by_id(watchlist_id)
    if watchlist is None:
        raise WatchlistNotFoundError(f"No watchlist with id {watchlist_id}")
    if watchlist.user_id != requesting_user_id:
        raise WatchlistOwnershipError(
            f"User {requesting_user_id} does not own watchlist {watchlist_id}"
        )
    return watchlist
