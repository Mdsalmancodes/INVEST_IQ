"""Protocol for obtaining current market prices — defined here (application
layer) rather than domain, since "current price" is an external, time-
varying fact, not a domain invariant. Phase 3 has no live market-data
ingestion yet (that is Document 8 §24's Market Data Foundation phase, not
yet built) — a stub/test-double implementation is used for now via DI, with
a real implementation swapped in once Phase 4 exists. This is the upgrade
path: PortfolioCalculationService's logic does not change at all when the
real provider replaces the stub.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.portfolio.value_objects import InstrumentId, Money


class PriceProvider(Protocol):
    async def get_current_price(self, instrument_id: InstrumentId) -> Money | None:
        """Returns None if no price is currently available (e.g. instrument
        not yet covered by market data) — callers must handle this
        gracefully (Document 6 §16's "no silent failure" rule), typically
        by excluding that holding from price-dependent calculations and
        surfacing a partial-data indicator rather than crashing."""
        ...

    async def get_previous_close(self, instrument_id: InstrumentId) -> Money | None:
        """Used for Daily Gain/Loss — the prior trading session's close."""
        ...
