"""Centralized exception handling for the market_data bounded context —
mirrors src.presentation.portfolio_exception_handlers's pattern.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from src.domain.market_data.exceptions import (
    AllProvidersFailedError,
    InstrumentNotFoundError,
    InvalidCorporateActionError,
    InvalidIntervalError,
    InvalidOhlcvBarError,
    InvalidPriceError,
    MarketDataDomainError,
    NoQuoteAvailableError,
)

_EXCEPTION_STATUS_MAP: dict[type[MarketDataDomainError], int] = {
    InstrumentNotFoundError: status.HTTP_404_NOT_FOUND,
    NoQuoteAvailableError: status.HTTP_404_NOT_FOUND,
    AllProvidersFailedError: status.HTTP_503_SERVICE_UNAVAILABLE,
    InvalidIntervalError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvalidPriceError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvalidOhlcvBarError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvalidCorporateActionError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def raise_market_data_exception_as_http(exc: MarketDataDomainError) -> None:
    status_code = _EXCEPTION_STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc
