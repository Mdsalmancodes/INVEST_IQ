"""SqlAlchemyAuditLogRepository — implements
src.domain.auth.repositories.AuditLogRepository."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.auth.entities import AuditLogEntry
from src.infrastructure.persistence.postgres.models import AuditLogModel


class SqlAlchemyAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, entry: AuditLogEntry) -> None:
        model = AuditLogModel(
            id=entry.id.value,
            user_id=entry.user_id.value if entry.user_id is not None else None,
            action=entry.action,
            resource_type=entry.resource_type,
            # AuditLogEntry.resource_id is a str at the domain layer (kept
            # generic there since not every resource type is necessarily a
            # UUID-keyed aggregate) — the audit_logs table's resource_id
            # column IS uuid-typed (Document 3 §8.1), so it is converted here
            # at the infrastructure boundary, not silently passed through.
            resource_id=uuid.UUID(entry.resource_id) if entry.resource_id is not None else None,
            ip_address=entry.ip_address,
            metadata_=entry.metadata,
        )
        self._session.add(model)
        await self._session.flush()
