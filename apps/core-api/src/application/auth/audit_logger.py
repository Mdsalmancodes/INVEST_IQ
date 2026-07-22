"""Audit logging service — Document 5 §14.1 / Document 6 §15.6.

Thin wrapper around AuditLogRepository that constructs a well-formed
AuditLogEntry from a security-relevant event, so use cases call one method
(`record`) rather than constructing the entity by hand each time.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.auth.entities import AuditLogEntry
from src.domain.auth.repositories import AuditLogRepository
from src.domain.auth.value_objects import UserId


class AuditLogger:
    def __init__(self, repository: AuditLogRepository) -> None:
        self._repository = repository

    async def record(
        self,
        *,
        action: str,
        user_id: UserId | None,
        ip_address: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        entry = AuditLogEntry(
            id=UserId.new(),
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            metadata=metadata or {},
            created_at=datetime.now(UTC),
        )
        await self._repository.save(entry)
