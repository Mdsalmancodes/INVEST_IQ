"""Dependency-injection wiring for the AI proxy — mirrors
src.presentation.dependencies.watchlist_use_cases's pattern (plain FastAPI
Depends() composition, no custom container).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ai_proxy.ai_service_client import AiServiceClient
from src.application.auth.audit_logger import AuditLogger
from src.config import Settings, get_settings
from src.infrastructure.http.ai_service_client import HttpAiServiceClient
from src.infrastructure.http.ai_service_http_client import get_ai_service_http_client
from src.infrastructure.http.mock_ai_service_client import MockAiServiceClient
from src.infrastructure.persistence.postgres.repositories.audit_log_repository import (
    SqlAlchemyAuditLogRepository,
)
from src.infrastructure.persistence.postgres.session import get_db_session


def get_ai_service_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AiServiceClient:
    if settings.ai_service_mode == "mock":
        return MockAiServiceClient()
    return HttpAiServiceClient(
        base_url=settings.ai_service_base_url,
        internal_service_token=settings.internal_service_token.get_secret_value(),
        timeout_seconds=settings.ai_service_request_timeout_seconds,
        client=get_ai_service_http_client(),
    )


def get_audit_logger(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuditLogger:
    """Reused as-is from src.application.auth.audit_logger — this is the
    first non-auth use of it, gated behind Phase 8's Admin-only model
    train/retrain/delete actions per Document 6 §15.6's audit-logged
    security-actions list ('admin actions on other users' data')."""
    return AuditLogger(SqlAlchemyAuditLogRepository(session))
