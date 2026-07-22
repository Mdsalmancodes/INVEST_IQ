"""Pydantic request/response DTOs for portfolio endpoints.

Per Document 2 §5.3: presentation-layer concern, distinct from domain
entities/value objects. All monetary/quantity fields are serialized as
strings (not float) to avoid IEEE-754 precision loss over JSON — the client
is responsible for parsing them back into a decimal type, matching the
same Decimal-never-float discipline Document 3 §3.4 rule #2 requires
server-side.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreatePortfolioRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    base_currency: str = Field(default="USD", min_length=3, max_length=3)
    is_paper: bool = Field(default=True)


class UpdatePortfolioRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_currency: str | None = Field(default=None, min_length=3, max_length=3)


class PortfolioResponse(BaseModel):
    id: str
    user_id: str
    name: str
    base_currency: str
    is_paper: bool
    created_at: str
    updated_at: str


class PortfolioListResponse(BaseModel):
    items: list[PortfolioResponse]
    total_count: int
    page: int
    page_size: int


class AddTransactionRequest(BaseModel):
    type: str = Field(
        ...,
        description="buy|sell|dividend|split|transfer_in|transfer_out|deposit|withdrawal",
    )
    executed_at: str = Field(..., description="ISO-8601 datetime")
    instrument_id: str | None = Field(default=None)
    quantity: str | None = Field(default=None, description="Decimal string")
    price: str | None = Field(default=None, description="Decimal string")
    fees: str = Field(default="0", description="Decimal string")
    split_ratio: float | None = Field(default=None, gt=0)
    related_portfolio_id: str | None = Field(default=None)
    cash_amount: str | None = Field(default=None, description="Decimal string")


class TransactionResponse(BaseModel):
    id: str
    portfolio_id: str
    instrument_id: str | None
    type: str
    quantity: str | None
    price: str | None
    fees: str
    split_ratio: float | None
    related_portfolio_id: str | None
    cash_amount: str | None
    executed_at: str
    created_at: str
    realized_gain: str | None = None


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total_count: int
    page: int
    page_size: int


class HoldingResponse(BaseModel):
    id: str
    instrument_id: str
    quantity: str
    average_cost: str


class HoldingListResponse(BaseModel):
    items: list[HoldingResponse]


class HoldingSummaryResponse(BaseModel):
    instrument_id: str
    quantity: str
    average_buy_price: str
    current_price: str | None
    market_value: str | None
    unrealized_gain: str | None
    allocation_pct: str | None
    daily_gain: str | None


class PortfolioSummaryResponse(BaseModel):
    portfolio_id: str
    total_investment: str
    current_value: str
    profit_loss: str
    profit_loss_pct: str
    realized_gain: str
    unrealized_gain: str
    dividend_income: str
    daily_gain: str
    holdings: list[HoldingSummaryResponse]
    holdings_missing_price: list[str]
