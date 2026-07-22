"""CreateWatchlistUseCase, DeleteWatchlistUseCase."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.watchlist.ownership import get_owned_watchlist_or_raise
from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.repositories import WatchlistRepository
from src.domain.watchlist.value_objects import WatchlistId


@dataclass(frozen=True, slots=True)
class CreateWatchlistCommand:
    user_id: str
    name: str
    is_default: bool = False


class CreateWatchlistUseCase:
    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        self._watchlist_repository = watchlist_repository

    async def execute(self, command: CreateWatchlistCommand) -> Watchlist:
        is_default = command.is_default
        if is_default:
            # Application-layer defense-in-depth companion to the DB's
            # partial unique index (idx_watchlists_user_default, ADR-0004):
            # demote any existing default watchlist first, so this new one
            # can safely become the default without violating the
            # constraint or leaving two defaults momentarily inconsistent
            # in the domain layer's view.
            current_default = await self._watchlist_repository.get_default_for_user(command.user_id)
            if current_default is not None:
                current_default.unmark_as_default()
                await self._watchlist_repository.save(current_default)

        watchlist = Watchlist.create(
            user_id=command.user_id, name=command.name, is_default=is_default
        )
        await self._watchlist_repository.save(watchlist)
        return watchlist


class DeleteWatchlistUseCase:
    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        self._watchlist_repository = watchlist_repository

    async def execute(self, watchlist_id: WatchlistId, requesting_user_id: str) -> None:
        await get_owned_watchlist_or_raise(
            self._watchlist_repository, watchlist_id, requesting_user_id
        )
        await self._watchlist_repository.delete(watchlist_id)
