"""ListLoginHistoryUseCase — per ADR-0002, the user-facing "recent logins"
read model."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.auth.entities import LoginHistoryEntry
from src.domain.auth.repositories import LoginHistoryRepository
from src.domain.auth.value_objects import UserId


@dataclass(frozen=True, slots=True)
class ListLoginHistoryCommand:
    user_id: UserId
    limit: int = 20


class ListLoginHistoryUseCase:
    def __init__(self, login_history_repository: LoginHistoryRepository) -> None:
        self._login_history_repository = login_history_repository

    async def execute(self, command: ListLoginHistoryCommand) -> list[LoginHistoryEntry]:
        return await self._login_history_repository.list_for_user(
            command.user_id, limit=command.limit
        )
