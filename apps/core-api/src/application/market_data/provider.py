"""Provider Protocols for the market_data bounded context.

Per Document 5 §11.1: "no business logic anywhere in the platform ever
references a vendor SDK or vendor-specific field name directly. Everything
goes through a MarketDataProvider interface." Defined here (application
layer, not domain) since a market-data vendor is an external, time-varying
data source — the same rationale already applied to Portfolio's
PriceProvider Protocol in src/application/portfolio/price_provider.py.

Per the founder's explicit Phase 4 scope, split into 3 focused Protocols
(HistoricalDataProvider, RealtimeQuoteProvider, plus the combining
MarketDataProvider) rather than Document 5's single 4-method interface —
this lets a provider implement only what it's actually capable of (e.g. a
provider with no real-time capability can implement HistoricalDataProvider
without pretending to support streaming), and lets ProviderRouter route
each capability independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from src.domain.market_data.value_objects import Interval, Price


@dataclass(frozen=True, slots=True)
class QuoteResult:
    """A single point-in-time quote from a provider — the internal DTO
    vendor adapters normalize into (Document 5 §11.2 stage 3's
    Anti-Corruption Layer). Deliberately keyed by `symbol`, not
    InstrumentId — a provider only ever knows the vendor's symbol string;
    resolving that to our internal instrument UUID is an application-layer
    concern (the use case already has the Instrument looked up by symbol),
    not something a provider adapter should have to fake or guess.
    """

    symbol: str
    price: Price
    previous_close: Price | None
    as_of: datetime
    source: str


@dataclass(frozen=True, slots=True)
class BarResult:
    """A single OHLCV bar from a provider, pre-domain-validation — kept
    distinct from the domain's OhlcvBar entity since a provider's raw
    response may (rarely) fail domain validation and the ingestion
    pipeline's Validate & Dedupe stage (Document 5 §11.2 stage 2) needs a
    place to reject bad data before it becomes a domain entity. Keyed by
    `symbol`, not InstrumentId — see QuoteResult's docstring for why."""

    symbol: str
    interval: Interval
    bar_time: datetime
    open: Price
    high: Price
    low: Price
    close: Price
    volume: int
    is_closed: bool
    source: str


class HistoricalDataProvider(Protocol):
    async def get_bars(
        self, symbol: str, interval: Interval, start: date, end: date
    ) -> tuple[BarResult, ...]: ...


class RealtimeQuoteProvider(Protocol):
    async def get_quote(self, symbol: str) -> QuoteResult: ...


class MarketDataProvider(HistoricalDataProvider, RealtimeQuoteProvider, Protocol):
    """The combined capability — most providers implement both; a
    provider that only implements one of the two narrower Protocols can
    still be used wherever only that capability is needed."""

    @property
    def name(self) -> str:
        """Provider identifier for logging/audit and the `source` field
        persisted on every OhlcvBar (Document 5 §11.2 stage 4)."""
        ...
