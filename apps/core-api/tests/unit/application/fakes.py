"""In-memory fake repositories for application-layer unit tests.

Per Document 6 §16.2: application use cases are unit-tested "with mocked
repository interfaces" — these fakes implement the domain Protocols
(src.domain.auth.repositories) in-memory, giving real behavior (not
MagicMock stand-ins that would let a use case call the wrong method
signature silently) without any actual I/O.
"""

from __future__ import annotations

from datetime import datetime

from src.domain.auth.entities import AuditLogEntry, LoginHistoryEntry, RefreshToken, User
from src.domain.auth.value_objects import Email, UserId


class FakeUserRepository:
    def __init__(self) -> None:
        self._by_id: dict[UserId, User] = {}

    async def save(self, user: User) -> None:
        self._by_id[user.id] = user

    async def get_by_id(self, user_id: UserId) -> User | None:
        return self._by_id.get(user_id)

    async def get_by_email(self, email: Email) -> User | None:
        for user in self._by_id.values():
            if user.email == email:
                return user
        return None

    async def exists_with_email(self, email: Email) -> bool:
        return await self.get_by_email(email) is not None


class FakeRefreshTokenRepository:
    def __init__(self) -> None:
        self._by_hash: dict[str, RefreshToken] = {}

    async def save(self, token: RefreshToken) -> None:
        self._by_hash[token.token_hash] = token

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        return self._by_hash.get(token_hash)

    async def revoke_all_for_user(self, user_id: UserId, at: datetime) -> None:
        for token in self._by_hash.values():
            if token.user_id == user_id and not token.is_revoked:
                token.revoke(at)


class FakeLoginHistoryRepository:
    def __init__(self) -> None:
        self.entries: list[LoginHistoryEntry] = []

    async def save(self, entry: LoginHistoryEntry) -> None:
        self.entries.append(entry)

    async def list_for_user(
        self, user_id: UserId, limit: int = 20
    ) -> list[LoginHistoryEntry]:
        matching = [e for e in self.entries if e.user_id == user_id]
        return sorted(matching, key=lambda e: e.created_at, reverse=True)[:limit]


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    async def save(self, entry: AuditLogEntry) -> None:
        self.entries.append(entry)
