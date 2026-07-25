"""Pydantic request/response DTOs for alert endpoints.

Per Document 2 §5.3: presentation-layer concern, distinct from domain
entities/value objects, matching watchlist_dto.py's decimal-as-string
discipline for any monetary/threshold field.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ConditionTypeLiteral = Literal["price_above", "price_below", "pct_change", "rsi_threshold"]


class CreateAlertRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    condition_type: ConditionTypeLiteral
    threshold: str = Field(..., description="Decimal string")
    is_recurring: bool = Field(default=False)
    cooldown_minutes: int = Field(default=0, ge=0)


class UpdateAlertRequest(BaseModel):
    condition_type: ConditionTypeLiteral | None = Field(default=None)
    threshold: str | None = Field(default=None, description="Decimal string")
    is_recurring: bool | None = Field(default=None)
    cooldown_minutes: int | None = Field(default=None, ge=0)
    is_active: bool | None = Field(default=None)


class AlertResponse(BaseModel):
    id: str
    user_id: str
    instrument_id: str
    symbol: str | None = None
    condition_type: str
    threshold: str = Field(..., description="Decimal string")
    is_recurring: bool
    cooldown_minutes: int
    is_active: bool
    triggered_at: str | None = Field(default=None, description="ISO-8601 datetime")
    created_at: str


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    total_count: int
    page: int
    page_size: int
