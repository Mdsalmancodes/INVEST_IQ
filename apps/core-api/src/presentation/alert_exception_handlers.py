"""Centralized exception handling for the alerts bounded context — mirrors
src.presentation.watchlist_exception_handlers's pattern.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from src.domain.alerts.exceptions import (
    AlertDomainError,
    AlertNotFoundError,
    AlertOwnershipError,
    DuplicateAlertError,
    InvalidAlertConditionError,
    InvalidCooldownError,
)

_EXCEPTION_STATUS_MAP: dict[type[AlertDomainError], int] = {
    AlertNotFoundError: status.HTTP_404_NOT_FOUND,
    AlertOwnershipError: status.HTTP_403_FORBIDDEN,
    DuplicateAlertError: status.HTTP_409_CONFLICT,
    InvalidAlertConditionError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvalidCooldownError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def raise_alert_exception_as_http(exc: AlertDomainError) -> None:
    status_code = _EXCEPTION_STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc
