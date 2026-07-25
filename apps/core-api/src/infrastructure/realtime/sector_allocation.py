"""sector_allocation.py — Phase 9's "Sector Allocation" / "Investment
Distribution" requirement, layered ON TOP OF Phase 3's frozen
PortfolioCalculationService rather than modifying it.

Deliberately placed in infrastructure/realtime/ (not
application/portfolio/) to keep it clearly scoped as Phase-9-only
aggregation logic — PortfolioCalculationService.compute_summary() (a
completed, tested Phase 3 use case) is not touched by this phase at all;
this module only groups its ALREADY-COMPUTED per-holding market values
by each holding's Instrument.sector, which PortfolioCalculationService's
own HoldingSummary does not need to know about for its own concerns
(total investment/profit-loss/etc.).

A holding whose instrument has no `sector` value (Instrument.sector is
`str | None`, Document 3 §8.1 — not every curated instrument has sector
data populated) is grouped under an explicit "Unknown" bucket rather
than silently dropped from the distribution — a $0 or missing bucket
would make percentages not sum to 100%, which is a worse user-facing
defect than an honest "Unknown" slice.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.application.portfolio.calculation_service import PortfolioSummary
from src.domain.market_data.repositories import InstrumentRepository
from src.domain.portfolio.value_objects import InstrumentId, Money

_UNKNOWN_SECTOR = "Unknown"


@dataclass(frozen=True, slots=True)
class SectorAllocationEntry:
    sector: str
    market_value: Money
    allocation_pct: Decimal


async def compute_sector_allocation(
    summary: PortfolioSummary, instrument_repository: InstrumentRepository
) -> tuple[SectorAllocationEntry, ...]:
    """Groups `summary.holdings` (already computed by
    PortfolioCalculationService, unmodified) by each holding's
    Instrument.sector, summing market_value per sector bucket and
    computing each bucket's share of the total priced market value.
    Holdings excluded from `summary.current_value` (no available price,
    per PortfolioSummary.holdings_missing_price) are excluded here too,
    for the same reason PortfolioCalculationService excludes them from
    its own totals — a missing price cannot be attributed to any sector
    bucket's dollar value without corrupting the distribution."""
    totals_by_sector: dict[str, Decimal] = {}

    for holding in summary.holdings:
        if holding.market_value is None:
            continue
        sector = await _resolve_sector(holding.instrument_id, instrument_repository)
        totals_by_sector[sector] = (
            totals_by_sector.get(sector, Decimal("0")) + holding.market_value.amount
        )

    total_priced_value = sum(totals_by_sector.values(), Decimal("0"))
    if total_priced_value == 0:
        return ()

    return tuple(
        SectorAllocationEntry(
            sector=sector,
            market_value=Money(value),
            allocation_pct=(value / total_priced_value) * Decimal("100"),
        )
        for sector, value in sorted(totals_by_sector.items(), key=lambda kv: kv[1], reverse=True)
    )


async def _resolve_sector(
    instrument_id: InstrumentId, instrument_repository: InstrumentRepository
) -> str:
    instrument = await instrument_repository.get_by_id(instrument_id)
    if instrument is None or instrument.sector is None:
        return _UNKNOWN_SECTOR
    return instrument.sector
