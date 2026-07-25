"""Centralized exception handling for the notifications bounded context —
mirrors src.presentation.alert_exception_handlers's pattern.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from src.domain.notifications.exceptions import (
    InvalidDigestFrequencyError,
    NotificationDomainError,
    NotificationNotFoundError,
    NotificationOwnershipError,
)

_EXCEPTION_STATUS_MAP: dict[type[NotificationDomainError], int] = {
    NotificationNotFoundError: status.HTTP_404_NOT_FOUND,
    NotificationOwnershipError: status.HTTP_403_FORBIDDEN,
    InvalidDigestFrequencyError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def raise_notification_exception_as_http(exc: NotificationDomainError) -> None:
    status_code = _EXCEPTION_STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc
