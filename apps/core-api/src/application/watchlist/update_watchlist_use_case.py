"""UpdateWatchlistUseCase — rename and/or set-as-default."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.watchlist.ownership import get_owned_watchlist_or_raise
from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.repositories import WatchlistRepository
from src.domain.watchlist.value_objects import WatchlistId


@dataclass(frozen=True, slots=True)
class UpdateWatchlistCommand:
    watchlist_id: WatchlistId
    requesting_user_id: str
    name: str | None = None
    is_default: bool | None = None


class UpdateWatchlistUseCase:
    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        self._watchlist_repository = watchlist_repository

    async def execute(self, command: UpdateWatchlistCommand) -> Watchlist:
        watchlist = await get_owned_watchlist_or_raise(
            self._watchlist_repository, command.watchlist_id, command.requesting_user_id
        )

        if command.name is not None:
            watchlist.rename(command.name)

        if command.is_default is True:
            current_default = await self._watchlist_repository.get_default_for_user(
                command.requesting_user_id
            )
            if current_default is not None and current_default.id != watchlist.id:
                current_default.unmark_as_default()
                await self._watchlist_repository.save(current_default)
            watchlist.mark_as_default()
        elif command.is_default is False:
            watchlist.unmark_as_default()

        await self._watchlist_repository.save(watchlist)
        return watchlist
