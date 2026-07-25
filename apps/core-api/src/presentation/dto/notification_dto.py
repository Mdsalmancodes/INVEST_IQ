"""Pydantic request/response DTOs for notification endpoints.

Per Document 2 §5.3: presentation-layer concern, distinct from domain
entities/value objects, matching alert_dto.py's conventions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DigestFrequencyLiteral = Literal["off", "daily", "weekly"]


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    type: str
    title: str
    body: str
    metadata: dict[str, object] = Field(default_factory=dict)
    is_read: bool
    read_at: str | None = Field(default=None, description="ISO-8601 datetime")
    created_at: str


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total_count: int
    unread_count: int
    page: int
    page_size: int


class MarkAllAsReadResponse(BaseModel):
    marked_count: int


class NotificationPreferencesResponse(BaseModel):
    user_id: str
    price_alerts_email: bool
    price_alerts_push: bool
    digest_frequency: str
    quiet_hours_start: str | None = Field(default=None, description="HH:MM:SS")
    quiet_hours_end: str | None = Field(default=None, description="HH:MM:SS")


class UpdateNotificationPreferencesRequest(BaseModel):
    price_alerts_email: bool | None = Field(default=None)
    price_alerts_push: bool | None = Field(default=None)
    digest_frequency: DigestFrequencyLiteral | None = Field(default=None)
    quiet_hours_start: str | None = Field(default=None, description="HH:MM:SS")
    quiet_hours_end: str | None = Field(default=None, description="HH:MM:SS")
    clear_quiet_hours: bool = Field(default=False)
