"""Pydantic request/response DTOs for watchlist endpoints.

Per Document 2 §5.3: presentation-layer concern, distinct from domain
entities/value objects, matching portfolio_dto.py's decimal-as-string
discipline for any monetary field.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateWatchlistRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_default: bool = Field(default=False)


class UpdateWatchlistRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_default: bool | None = Field(default=None)


class AddWatchlistItemRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)


class UpdateWatchlistItemRequest(BaseModel):
    is_pinned: bool | None = Field(default=None)
    position: int | None = Field(default=None, ge=0)


class WatchlistItemQuoteResponse(BaseModel):
    """Live market-data enrichment for a single watchlist item — Phase 4/5
    integration point. `is_delayed` mirrors GetCurrentPriceUseCase's
    is_stale_fallback flag (renamed for the frontend-facing "delayed
    indicator" the founder explicitly requested), so a stale/cached quote
    is always honestly labeled, never silently presented as live.
    """

    price: str | None = Field(default=None, description="Decimal string")
    previous_close: str | None = Field(default=None, description="Decimal string")
    daily_change: str | None = Field(default=None, description="Decimal string")
    daily_change_pct: str | None = Field(default=None, description="Decimal string")
    source: str | None = None
    is_delayed: bool = False
    last_updated: str | None = Field(default=None, description="ISO-8601 datetime")
    error: str | None = Field(
        default=None, description="Set if this item's quote could not be fetched"
    )


class WatchlistItemResponse(BaseModel):
    id: str
    instrument_id: str
    symbol: str | None = None
    position: int
    is_pinned: bool
    added_at: str
    quote: WatchlistItemQuoteResponse | None = None


class WatchlistResponse(BaseModel):
    id: str
    user_id: str
    name: str
    is_default: bool
    created_at: str
    updated_at: str
    items: list[WatchlistItemResponse] = Field(default_factory=list)
    market_status: str | None = Field(
        default=None, description="open|closed|pre-market|after-hours"
    )


class WatchlistSummaryResponse(BaseModel):
    """Lighter-weight shape for the list endpoint — no items/quotes, since
    fetching live prices for every item across every watchlist on a list
    call would be an unbounded number of quote lookups. Full item/quote
    detail is only returned by GET /watchlists/{id}.
    """

    id: str
    user_id: str
    name: str
    is_default: bool
    created_at: str
    updated_at: str
    item_count: int


class WatchlistListResponse(BaseModel):
    items: list[WatchlistSummaryResponse]
    total_count: int
    page: int
    page_size: int
