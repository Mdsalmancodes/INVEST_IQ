"""Centralized exception handling for the portfolio bounded context —
mirrors src.presentation.exception_handlers's pattern for auth.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from src.domain.portfolio.exceptions import (
    HoldingNotFoundError,
    InsufficientHoldingQuantityError,
    InvalidMoneyAmountError,
    InvalidQuantityError,
    InvalidTransactionError,
    PortfolioDomainError,
    PortfolioNotFoundError,
    PortfolioOwnershipError,
    TransactionNotFoundError,
)

_EXCEPTION_STATUS_MAP: dict[type[PortfolioDomainError], int] = {
    PortfolioNotFoundError: status.HTTP_404_NOT_FOUND,
    HoldingNotFoundError: status.HTTP_404_NOT_FOUND,
    TransactionNotFoundError: status.HTTP_404_NOT_FOUND,
    PortfolioOwnershipError: status.HTTP_403_FORBIDDEN,
    InsufficientHoldingQuantityError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvalidTransactionError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvalidMoneyAmountError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvalidQuantityError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def raise_portfolio_exception_as_http(exc: PortfolioDomainError) -> None:
    status_code = _EXCEPTION_STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc
