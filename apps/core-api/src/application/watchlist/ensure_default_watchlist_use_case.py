"""EnsureDefaultWatchlistUseCase — provisions a user's first (default)
watchlist on first access, per ADR-0004's design note.

NOT wired into registration itself (Auth/Phase 2 is frozen and must not be
modified) — instead, this is called defensively from the watchlist
dashboard's list endpoint (GetWatchlistDashboardUseCase / the
ListWatchlistsUseCase call path) whenever a user has zero watchlists, so
every user reaches exactly one default watchlist lazily on first real use
rather than eagerly at signup time.
"""

from __future__ import annotations

from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.repositories import WatchlistRepository

_DEFAULT_WATCHLIST_NAME = "My Watchlist"


class EnsureDefaultWatchlistUseCase:
    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        self._watchlist_repository = watchlist_repository

    async def execute(self, user_id: str) -> Watchlist | None:
        """Returns the newly-created default watchlist if one was
        provisioned, or None if the user already has at least one
        watchlist (nothing to do)."""
        existing_count = await self._watchlist_repository.count_for_user(user_id)
        if existing_count > 0:
            return None

        watchlist = Watchlist.create(user_id=user_id, name=_DEFAULT_WATCHLIST_NAME, is_default=True)
        await self._watchlist_repository.save(watchlist)
        return watchlist
