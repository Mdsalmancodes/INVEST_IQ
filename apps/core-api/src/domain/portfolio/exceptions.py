"""Domain exceptions for the portfolio bounded context.

Per Document 5 §14.3: domain layer raises specific exceptions, never
generic Exception; the presentation layer's centralized exception handler
maps each of these to an HTTP status (extending the pattern established in
Phase 2's src.presentation.exception_handlers).
"""

from __future__ import annotations


class PortfolioDomainError(Exception):
    """Base class for all portfolio domain exceptions."""


class InvalidMoneyAmountError(PortfolioDomainError):
    pass


class InvalidQuantityError(PortfolioDomainError):
    pass


class PortfolioNotFoundError(PortfolioDomainError):
    pass


class HoldingNotFoundError(PortfolioDomainError):
    pass


class TransactionNotFoundError(PortfolioDomainError):
    pass


class InsufficientHoldingQuantityError(PortfolioDomainError):
    """Raised when a sell/transfer_out/withdrawal would reduce a holding's
    quantity below zero — Document 3 §3.4 rule #1's aggregate invariant."""


class InvalidTransactionError(PortfolioDomainError):
    """Raised for a structurally invalid transaction (e.g. a `split`
    transaction with no split_ratio, or a `transfer` referencing a
    related_portfolio_id the user does not own — ADR-0003)."""


class PortfolioOwnershipError(PortfolioDomainError):
    """Raised when an operation is attempted on a portfolio the current
    user does not own — Document 3 §7.5's resource-level ownership rule,
    applied to the portfolio context specifically."""
