"""Domain exceptions for the market_data bounded context.

Per Document 5 §14.3: domain layer raises specific exceptions, never
generic Exception; the presentation layer's centralized exception handler
maps each of these to an HTTP status, following the same pattern already
established for auth and portfolio.
"""

from __future__ import annotations


class MarketDataDomainError(Exception):
    """Base class for all market_data domain exceptions."""


class InvalidPriceError(MarketDataDomainError):
    pass


class InvalidIntervalError(MarketDataDomainError):
    pass


class InvalidOhlcvBarError(MarketDataDomainError):
    """Raised for a structurally invalid OHLCV bar (e.g. high < low)."""


class InvalidCorporateActionError(MarketDataDomainError):
    """Raised for a structurally invalid corporate action (e.g. a 'split'
    with no ratio, or a 'dividend' with no cash_amount)."""


class InstrumentNotFoundError(MarketDataDomainError):
    pass


class NoQuoteAvailableError(MarketDataDomainError):
    """Raised when no current price is available for an instrument from
    any configured provider — distinct from InstrumentNotFoundError since
    the instrument may exist but simply have no live quote right now
    (e.g. all providers are down, or the instrument's market is closed
    and no last-close is cached yet)."""


class AllProvidersFailedError(MarketDataDomainError):
    """Raised by ProviderRouter when every configured provider in the
    failover chain has failed for a given request — Document 5 §11.1's
    provider abstraction exists precisely so this is the ONLY place a
    caller needs to handle "the vendor is unavailable," never a
    vendor-specific exception type leaking up."""
