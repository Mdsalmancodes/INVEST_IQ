"""Pydantic request/response DTOs for market_data endpoints.

Per Document 2 §5.3 and the same Decimal-string-never-float discipline
established for portfolio DTOs — all price/quantity/volume-adjacent
fields that carry monetary precision are serialized as strings.
"""

from __future__ import annotations

from pydantic import BaseModel


class CurrentPriceResponse(BaseModel):
    symbol: str
    price: str
    previous_close: str | None
    source: str
    is_stale_fallback: bool


class PricePointResponse(BaseModel):
    as_of: str
    price: str


class HistoricalPricesResponse(BaseModel):
    symbol: str
    interval: str
    points: list[PricePointResponse]
    data_completeness: str


class OhlcvBarResponse(BaseModel):
    bar_time: str
    open: str
    high: str
    low: str
    close: str
    adjusted_close: str
    volume: int
    is_closed: bool
    source: str


class OhlcvBarsResponse(BaseModel):
    symbol: str
    interval: str
    bars: list[OhlcvBarResponse]
    data_completeness: str


class CorporateActionResponse(BaseModel):
    id: str
    action_type: str
    ratio: str | None
    cash_amount: str | None
    ex_date: str
    announced_at: str | None


class CorporateActionListResponse(BaseModel):
    items: list[CorporateActionResponse]


class MarketStatusResponse(BaseModel):
    is_open: bool
    session: str
    as_of: str
    next_open: str | None


class InstrumentSearchResultResponse(BaseModel):
    id: str
    symbol: str
    exchange: str
    name: str
    asset_type: str
    currency: str


class InstrumentSearchResponse(BaseModel):
    items: list[InstrumentSearchResultResponse]
