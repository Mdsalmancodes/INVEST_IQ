"""Domain exceptions for the watchlist bounded context.

Per Document 5 §14.3: domain layer raises specific exceptions, never
generic Exception; the presentation layer's centralized exception handler
maps each of these to an HTTP status, matching the established
portfolio/market_data exception-mapping pattern.
"""

from __future__ import annotations


class WatchlistDomainError(Exception):
    """Base class for all watchlist domain exceptions."""


class WatchlistNotFoundError(WatchlistDomainError):
    pass


class WatchlistItemNotFoundError(WatchlistDomainError):
    pass


class DuplicateWatchlistItemError(WatchlistDomainError):
    """Raised when adding a symbol already present in the watchlist —
    mirrors the DB-level UNIQUE(watchlist_id, instrument_id) constraint at
    the domain layer too, so the invariant is enforced before a repository
    round-trip, not only caught as a database integrity error."""


class WatchlistOwnershipError(WatchlistDomainError):
    """Raised when an operation is attempted on a watchlist the current
    user does not own — Document 3 §7.5's resource-level ownership rule,
    applied to the watchlist context (matches PortfolioOwnershipError)."""


class InvalidWatchlistNameError(WatchlistDomainError):
    pass


class DefaultWatchlistAlreadyExistsError(WatchlistDomainError):
    """Raised if application logic ever attempts to mark a second watchlist
    as default for the same user — ADR-0004's at-most-one-default-per-user
    invariant, enforced at the domain layer as a defense-in-depth companion
    to the DB's partial unique index (idx_watchlists_user_default)."""
