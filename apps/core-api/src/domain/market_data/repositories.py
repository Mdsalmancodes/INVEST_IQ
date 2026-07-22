"""Repository interfaces (Protocols) for the market_data bounded context.

Per docs/architecture/02-clean-architecture-folder-frontend.md §4.1: these
live in the domain layer and are implemented by infrastructure — the
dependency arrow always points inward.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from src.domain.market_data.entities import CorporateAction, Instrument, OhlcvBar
from src.domain.market_data.value_objects import CorporateActionId, InstrumentId, Interval


class InstrumentRepository(Protocol):
    async def save(self, instrument: Instrument) -> None: ...

    async def get_by_id(self, instrument_id: InstrumentId) -> Instrument | None: ...

    async def get_by_symbol(self, symbol: str) -> Instrument | None:
        """Resolves via the globally-unique-symbol partial index
        (Document 3 §8.1 revision) — callers never need to disambiguate
        by exchange for the curated V1 instrument universe."""
        ...

    async def search(self, query: str, limit: int = 20) -> tuple[Instrument, ...]:
        """Case-insensitive prefix/substring match on symbol or name."""
        ...


@dataclass(frozen=True, slots=True)
class OhlcvBarQuery:
    instrument_id: InstrumentId
    interval: Interval
    start: datetime | None = None
    end: datetime | None = None
    limit: int | None = None


class OhlcvBarRepository(Protocol):
    async def save(self, bar: OhlcvBar) -> None:
        """Upsert semantics keyed by (instrument_id, interval, bar_time) —
        Document 5 §11.2 stage 2's dedupe rule means a re-fetch of the
        same bar (e.g. an in-progress bar polled repeatedly before it
        closes) must overwrite, not duplicate."""
        ...

    async def save_many(self, bars: tuple[OhlcvBar, ...]) -> None:
        """Bulk upsert — used by the historical backfill job (Document 5
        §11.3's "bulk-insert via Postgres COPY... for performance")."""
        ...

    async def query(self, query: OhlcvBarQuery) -> tuple[OhlcvBar, ...]: ...

    async def get_latest_closed_bar(
        self, instrument_id: InstrumentId, interval: Interval
    ) -> OhlcvBar | None:
        """Used by RealPriceProvider as the "current price" fallback when
        no live quote is cached — the most recent closed bar's close."""
        ...

    async def apply_adjustment_factor_before_date(
        self, instrument_id: InstrumentId, before: date, factor: Decimal
    ) -> int:
        """Rescales adjusted_close for all bars strictly before `before`
        by `factor` — Document 5 §11.4's backward-adjustment cascade.
        Returns the count of bars updated."""
        ...


class CorporateActionRepository(Protocol):
    async def save(self, action: CorporateAction) -> None: ...

    async def get_by_id(self, action_id: CorporateActionId) -> CorporateAction | None: ...

    async def list_for_instrument(self, instrument_id: InstrumentId) -> tuple[CorporateAction, ...]:
        """Ordered by ex_date descending."""
        ...

    async def exists(self, instrument_id: InstrumentId, action_type: str, ex_date: date) -> bool:
        """Dedupe check against the UNIQUE(instrument_id, action_type,
        ex_date) constraint before inserting — avoids relying on catching
        an IntegrityError for expected-duplicate ingestion retries."""
        ...
