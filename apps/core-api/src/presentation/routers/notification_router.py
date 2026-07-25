"""notification_router.py — HTTP endpoints wiring all notification and
notification-preference use cases.

Every endpoint follows alert_router.py's established pattern: build
command/query -> call use case -> map domain exceptions to HTTP -> return
DTO. All notification_id path params are scoped by CurrentUser's user_id
(never accepted as a request body/query field for the owner identity) —
Document 3 §7.5's resource-level ownership enforcement. All endpoints
require authentication, matching Alerts/Watchlist's contrast with Market
Data's public endpoints, since notifications are private per-user
resources.

The preferences endpoints are registered on this same router (not a
separate notification_preferences_router) since they share the
"/api/v1/notifications" prefix and are a natural sub-resource
(/preferences), matching how Watchlist nests its items endpoints under
"/watchlists/{id}/items" rather than a separate router.
"""

from __future__ import annotations

from datetime import time
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.application.notifications.notification_use_cases import (
    ListNotificationsQuery,
    ListNotificationsUseCase,
    MarkAllNotificationsAsReadUseCase,
    MarkNotificationAsReadUseCase,
)
from src.application.notifications.preference_use_cases import (
    GetNotificationPreferencesUseCase,
    UpdateNotificationPreferencesCommand,
    UpdateNotificationPreferencesUseCase,
)
from src.domain.notifications.entities import Notification, NotificationPreferences
from src.domain.notifications.exceptions import NotificationDomainError
from src.domain.notifications.value_objects import NotificationId
from src.presentation.dependencies.auth import CurrentUser, get_current_user
from src.presentation.dependencies.notification_use_cases import (
    get_get_notification_preferences_use_case,
    get_list_notifications_use_case,
    get_mark_all_notifications_as_read_use_case,
    get_mark_notification_as_read_use_case,
    get_update_notification_preferences_use_case,
)
from src.presentation.dto.notification_dto import (
    MarkAllAsReadResponse,
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationResponse,
    UpdateNotificationPreferencesRequest,
)
from src.presentation.notification_exception_handlers import raise_notification_exception_as_http

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def _notification_to_response(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=str(notification.id),
        user_id=notification.user_id,
        type=notification.type,
        title=notification.title,
        body=notification.body,
        metadata=notification.metadata,
        is_read=notification.is_read,
        read_at=notification.read_at.isoformat() if notification.read_at is not None else None,
        created_at=notification.created_at.isoformat(),
    )


def _preferences_to_response(
    preferences: NotificationPreferences,
) -> NotificationPreferencesResponse:
    return NotificationPreferencesResponse(
        user_id=preferences.user_id,
        price_alerts_email=preferences.price_alerts_email,
        price_alerts_push=preferences.price_alerts_push,
        digest_frequency=preferences.digest_frequency,
        quiet_hours_start=(
            preferences.quiet_hours_start.isoformat()
            if preferences.quiet_hours_start is not None
            else None
        ),
        quiet_hours_end=(
            preferences.quiet_hours_end.isoformat()
            if preferences.quiet_hours_end is not None
            else None
        ),
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[ListNotificationsUseCase, Depends(get_list_notifications_use_case)],
    unread_only: Annotated[bool, Query()] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NotificationListResponse:
    result = await use_case.execute(
        ListNotificationsQuery(
            user_id=str(current_user.user_id),
            unread_only=unread_only,
            page=page,
            page_size=page_size,
        )
    )
    return NotificationListResponse(
        items=[_notification_to_response(n) for n in result.items],
        total_count=result.total_count,
        unread_count=result.unread_count,
        page=result.page,
        page_size=result.page_size,
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_as_read(
    notification_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[
        MarkNotificationAsReadUseCase, Depends(get_mark_notification_as_read_use_case)
    ],
) -> NotificationResponse:
    try:
        notification = await use_case.execute(
            NotificationId.from_string(notification_id), str(current_user.user_id)
        )
    except NotificationDomainError as exc:
        raise_notification_exception_as_http(exc)
        raise
    return _notification_to_response(notification)


@router.post("/read-all", response_model=MarkAllAsReadResponse)
async def mark_all_notifications_as_read(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[
        MarkAllNotificationsAsReadUseCase, Depends(get_mark_all_notifications_as_read_use_case)
    ],
) -> MarkAllAsReadResponse:
    marked_count = await use_case.execute(str(current_user.user_id))
    return MarkAllAsReadResponse(marked_count=marked_count)


@router.get("/preferences", response_model=NotificationPreferencesResponse)
async def get_notification_preferences(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[
        GetNotificationPreferencesUseCase, Depends(get_get_notification_preferences_use_case)
    ],
) -> NotificationPreferencesResponse:
    preferences = await use_case.execute(str(current_user.user_id))
    return _preferences_to_response(preferences)


@router.patch("/preferences", response_model=NotificationPreferencesResponse)
async def update_notification_preferences(
    body: UpdateNotificationPreferencesRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[
        UpdateNotificationPreferencesUseCase,
        Depends(get_update_notification_preferences_use_case),
    ],
) -> NotificationPreferencesResponse:
    try:
        preferences = await use_case.execute(
            UpdateNotificationPreferencesCommand(
                user_id=str(current_user.user_id),
                price_alerts_email=body.price_alerts_email,
                price_alerts_push=body.price_alerts_push,
                digest_frequency=body.digest_frequency,
                quiet_hours_start=(
                    time.fromisoformat(body.quiet_hours_start)
                    if body.quiet_hours_start is not None
                    else None
                ),
                quiet_hours_end=(
                    time.fromisoformat(body.quiet_hours_end)
                    if body.quiet_hours_end is not None
                    else None
                ),
                clear_quiet_hours=body.clear_quiet_hours,
            )
        )
    except NotificationDomainError as exc:
        raise_notification_exception_as_http(exc)
        raise
    return _preferences_to_response(preferences)
