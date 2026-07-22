"""RETIRED (Phase 4): Stub PriceProvider implementation used through
Phase 3, when no live market-data ingestion existed yet (Document 8 §24's
Market Data Foundation phase). Superseded by
src.infrastructure.market_data.real_price_provider.RealPriceProvider,
which is now wired into src.presentation.dependencies.portfolio_use_cases
per the upgrade path this module's own docstring specified. Kept in the
codebase (not deleted) as a record of the disclosed Phase 3 simplification
and its resolution — no longer referenced by any DI wiring.
"""

from __future__ import annotations

from src.domain.portfolio.value_objects import InstrumentId, Money


class NullPriceProvider:
    """Implements PriceProvider by always returning None. See module
    docstring — retired, no longer wired into DI as of Phase 4."""

    async def get_current_price(self, instrument_id: InstrumentId) -> Money | None:
        return None

    async def get_previous_close(self, instrument_id: InstrumentId) -> Money | None:
        return None
