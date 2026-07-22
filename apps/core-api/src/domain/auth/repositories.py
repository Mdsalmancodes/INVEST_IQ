"""Repository interfaces (Protocols) for the auth bounded context.

Per docs/architecture/02-clean-architecture-folder-frontend.md §4.1: these
live in the domain layer and are implemented by infrastructure — the
dependency arrow always points inward. Application-layer use cases depend on
these Protocols, never on a concrete SQLAlchemy/Redis implementation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.domain.auth.entities import AuditLogEntry, LoginHistoryEntry, RefreshToken, User
from src.domain.auth.value_objects import Email, UserId


class UserRepository(Protocol):
    async def save(self, user: User) -> None: ...

    async def get_by_id(self, user_id: UserId) -> User | None: ...

    async def get_by_email(self, email: Email) -> User | None: ...

    async def exists_with_email(self, email: Email) -> bool: ...


class RefreshTokenRepository(Protocol):
    async def save(self, token: RefreshToken) -> None: ...

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None: ...

    async def revoke_all_for_user(self, user_id: UserId, at: datetime) -> None: ...


class LoginHistoryRepository(Protocol):
    """Per ADR-0002."""

    async def save(self, entry: LoginHistoryEntry) -> None: ...

    async def list_for_user(self, user_id: UserId, limit: int = 20) -> list[LoginHistoryEntry]: ...


class AuditLogRepository(Protocol):
    async def save(self, entry: AuditLogEntry) -> None: ...
