"""alert_router.py — HTTP endpoints wiring all alert use cases.

Every endpoint follows watchlist_router.py's established pattern: build
command/query -> call use case -> map domain exceptions to HTTP -> return
DTO. All alert_id path params are scoped by CurrentUser's user_id (never
accepted as a request body/query field for the owner identity) — Document
3 §7.5's resource-level ownership enforcement. All 5 endpoints require
authentication, matching Watchlist's contrast with Market Data's public
endpoints, since alerts are private per-user resources.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.application.alerts.create_alert_use_case import (
    CreateAlertCommand,
    CreateAlertUseCase,
    DeleteAlertUseCase,
)
from src.application.alerts.get_alert_use_case import (
    GetAlertUseCase,
    ListAlertsQuery,
    ListAlertsUseCase,
)
from src.application.alerts.update_alert_use_case import UpdateAlertCommand, UpdateAlertUseCase
from src.domain.alerts.entities import Alert
from src.domain.alerts.exceptions import AlertDomainError
from src.domain.alerts.value_objects import AlertId
from src.domain.market_data.exceptions import MarketDataDomainError
from src.presentation.alert_exception_handlers import raise_alert_exception_as_http
from src.presentation.dependencies.alert_use_cases import (
    get_create_alert_use_case,
    get_delete_alert_use_case,
    get_get_alert_use_case,
    get_list_alerts_use_case,
    get_update_alert_use_case,
)
from src.presentation.dependencies.auth import CurrentUser, get_current_user
from src.presentation.dto.alert_dto import (
    AlertListResponse,
    AlertResponse,
    ConditionTypeLiteral,
    CreateAlertRequest,
    UpdateAlertRequest,
)
from src.presentation.market_data_exception_handlers import raise_market_data_exception_as_http

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def _raise_domain_exception_as_http(exc: Exception) -> None:
    if isinstance(exc, AlertDomainError):
        raise_alert_exception_as_http(exc)
    elif isinstance(exc, MarketDataDomainError):
        raise_market_data_exception_as_http(exc)
    raise exc


def _alert_to_response(alert: Alert) -> AlertResponse:
    return AlertResponse(
        id=str(alert.id),
        user_id=alert.user_id,
        instrument_id=str(alert.instrument_id),
        symbol=None,
        condition_type=alert.condition_type,
        threshold=str(alert.threshold),
        is_recurring=alert.is_recurring,
        cooldown_minutes=alert.cooldown_minutes,
        is_active=alert.is_active,
        triggered_at=alert.triggered_at.isoformat() if alert.triggered_at is not None else None,
        created_at=alert.created_at.isoformat(),
    )


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: CreateAlertRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[CreateAlertUseCase, Depends(get_create_alert_use_case)],
) -> AlertResponse:
    try:
        alert = await use_case.execute(
            CreateAlertCommand(
                user_id=str(current_user.user_id),
                symbol=body.symbol,
                condition_type=body.condition_type,
                threshold=Decimal(body.threshold),
                is_recurring=body.is_recurring,
                cooldown_minutes=body.cooldown_minutes,
            )
        )
    except (AlertDomainError, MarketDataDomainError) as exc:
        _raise_domain_exception_as_http(exc)
        raise
    response = _alert_to_response(alert)
    response.symbol = body.symbol.upper()
    return response


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[ListAlertsUseCase, Depends(get_list_alerts_use_case)],
    is_active: Annotated[bool | None, Query()] = None,
    sort_by: Annotated[str, Query()] = "created_at",
    sort_direction: Annotated[str, Query()] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AlertListResponse:
    result = await use_case.execute(
        ListAlertsQuery(
            user_id=str(current_user.user_id),
            is_active=is_active,
            sort_by=sort_by,  # type: ignore[arg-type]
            sort_direction=sort_direction,  # type: ignore[arg-type]
            page=page,
            page_size=page_size,
        )
    )
    return AlertListResponse(
        items=[_alert_to_response(a) for a in result.items],
        total_count=result.total_count,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[GetAlertUseCase, Depends(get_get_alert_use_case)],
) -> AlertResponse:
    try:
        alert = await use_case.execute(AlertId.from_string(alert_id), str(current_user.user_id))
    except AlertDomainError as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return _alert_to_response(alert)


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: str,
    body: UpdateAlertRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[UpdateAlertUseCase, Depends(get_update_alert_use_case)],
) -> AlertResponse:
    condition_type: ConditionTypeLiteral | None = body.condition_type
    try:
        alert = await use_case.execute(
            UpdateAlertCommand(
                alert_id=AlertId.from_string(alert_id),
                requesting_user_id=str(current_user.user_id),
                condition_type=condition_type,
                threshold=Decimal(body.threshold) if body.threshold is not None else None,
                is_recurring=body.is_recurring,
                cooldown_minutes=body.cooldown_minutes,
                is_active=body.is_active,
            )
        )
    except AlertDomainError as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return _alert_to_response(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_alert(
    alert_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[DeleteAlertUseCase, Depends(get_delete_alert_use_case)],
) -> None:
    try:
        await use_case.execute(AlertId.from_string(alert_id), str(current_user.user_id))
    except AlertDomainError as exc:
        _raise_domain_exception_as_http(exc)
        raise
