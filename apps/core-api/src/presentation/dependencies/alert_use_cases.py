"""Dependency-injection wiring for alert use cases — mirrors
src.presentation.dependencies.watchlist_use_cases's pattern.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.alerts.create_alert_use_case import CreateAlertUseCase, DeleteAlertUseCase
from src.application.alerts.get_alert_use_case import GetAlertUseCase, ListAlertsUseCase
from src.application.alerts.update_alert_use_case import UpdateAlertUseCase
from src.infrastructure.persistence.postgres.repositories.alert_repository import (
    SqlAlchemyAlertRepository,
)
from src.infrastructure.persistence.postgres.repositories.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from src.infrastructure.persistence.postgres.session import get_db_session


def get_create_alert_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CreateAlertUseCase:
    return CreateAlertUseCase(
        SqlAlchemyAlertRepository(session), SqlAlchemyInstrumentRepository(session)
    )


def get_get_alert_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GetAlertUseCase:
    return GetAlertUseCase(SqlAlchemyAlertRepository(session))


def get_list_alerts_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ListAlertsUseCase:
    return ListAlertsUseCase(SqlAlchemyAlertRepository(session))


def get_update_alert_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UpdateAlertUseCase:
    return UpdateAlertUseCase(SqlAlchemyAlertRepository(session))


def get_delete_alert_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DeleteAlertUseCase:
    return DeleteAlertUseCase(SqlAlchemyAlertRepository(session))
