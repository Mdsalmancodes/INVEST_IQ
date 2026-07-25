"""Tests for compute_sector_allocation — real PortfolioCalculationService
(Phase 3, unmodified) to produce a real PortfolioSummary, fakes only for
PriceProvider/TransactionRepository/InstrumentRepository, matching
test_calculation_service.py's own established convention exactly."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from src.application.portfolio.calculation_service import PortfolioCalculationService
from src.domain.market_data.entities import AssetType, Instrument
from src.domain.market_data.value_objects import InstrumentId as MarketDataInstrumentId
from src.domain.portfolio.entities import Portfolio, Transaction, TransactionType
from src.domain.portfolio.repositories import PageResult, TransactionFilter
from src.domain.portfolio.value_objects import (
    InstrumentId,
    Money,
    PortfolioId,
    Quantity,
    TransactionId,
)
from src.infrastructure.realtime.sector_allocation import compute_sector_allocation

NOW = datetime(2026, 1, 1, tzinfo=UTC)
TECH_INSTRUMENT = InstrumentId(uuid.uuid4())
HEALTH_INSTRUMENT = InstrumentId(uuid.uuid4())
UNKNOWN_SECTOR_INSTRUMENT = InstrumentId(uuid.uuid4())


class FakePriceProvider:
    def __init__(self, prices: dict[str, Decimal]) -> None:
        self._prices = prices

    async def get_current_price(self, instrument_id: InstrumentId) -> Money | None:
        raw = self._prices.get(str(instrument_id))
        return Money(raw) if raw is not None else None

    async def get_previous_close(self, instrument_id: InstrumentId) -> Money | None:
        return None


class FakeTransactionRepository:
    def __init__(self, transactions: list[Transaction]) -> None:
        self._transactions = transactions

    async def save(self, transaction: Transaction) -> None:
        self._transactions.append(transaction)

    async def get_by_id(self, transaction_id: TransactionId) -> Transaction | None:
        return None

    async def list_for_portfolio(
        self, portfolio_id: PortfolioId, filters: TransactionFilter
    ) -> PageResult:
        return PageResult(items=(), total_count=0, page=1, page_size=20)

    async def list_all_for_portfolio_unpaginated(
        self, portfolio_id: PortfolioId
    ) -> tuple[Transaction, ...]:
        return tuple(t for t in self._transactions if t.portfolio_id == portfolio_id)


class FakeInstrumentRepository:
    def __init__(self, instruments: dict[str, Instrument]) -> None:
        self._by_id = instruments

    async def get_by_id(self, instrument_id: InstrumentId) -> Instrument | None:
        return self._by_id.get(str(instrument_id))


def _instrument(instrument_id: InstrumentId, symbol: str, sector: str | None) -> Instrument:
    return Instrument(
        id=MarketDataInstrumentId(instrument_id.value),
        symbol=symbol,
        exchange="NASDAQ",
        name=f"{symbol} Inc.",
        asset_type=AssetType.EQUITY,
        currency="USD",
        sector=sector,
        industry=None,
        ipo_date=None,
        is_active=True,
        created_at=NOW,
    )


def _make_portfolio() -> Portfolio:
    return Portfolio(
        id=PortfolioId.new(),
        user_id="user-1",
        name="My Portfolio",
        base_currency="USD",
        is_paper=False,
        created_at=NOW,
        updated_at=NOW,
    )


def _make_buy(
    portfolio_id: PortfolioId, instrument_id: InstrumentId, quantity: str, price: str
) -> Transaction:
    return Transaction(
        id=TransactionId.new(),
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        type=TransactionType.BUY,
        quantity=Quantity(Decimal(quantity)),
        price=Money(Decimal(price)),
        fees=Money(Decimal("0")),
        split_ratio=None,
        related_portfolio_id=None,
        cash_amount=None,
        executed_at=NOW,
        created_at=NOW,
    )


class TestComputeSectorAllocation:
    async def test_groups_holdings_by_sector_and_computes_percentages(self) -> None:
        portfolio = _make_portfolio()
        portfolio.apply_transaction(_make_buy(portfolio.id, TECH_INSTRUMENT, "10", "100"))
        portfolio.apply_transaction(_make_buy(portfolio.id, HEALTH_INSTRUMENT, "5", "100"))

        price_provider = FakePriceProvider(
            {str(TECH_INSTRUMENT): Decimal("100"), str(HEALTH_INSTRUMENT): Decimal("100")}
        )
        calc_service = PortfolioCalculationService(price_provider, FakeTransactionRepository([]))
        summary = await calc_service.compute_summary(portfolio)

        instrument_repo = FakeInstrumentRepository(
            {
                str(TECH_INSTRUMENT): _instrument(TECH_INSTRUMENT, "TECH", "Technology"),
                str(HEALTH_INSTRUMENT): _instrument(HEALTH_INSTRUMENT, "HLTH", "Healthcare"),
            }
        )

        allocation = await compute_sector_allocation(summary, instrument_repo)  # type: ignore[arg-type]

        by_sector = {entry.sector: entry for entry in allocation}
        assert by_sector["Technology"].market_value.amount == Decimal("1000")
        assert by_sector["Healthcare"].market_value.amount == Decimal("500")
        # 1000/1500 = 66.67%, 500/1500 = 33.33%
        assert by_sector["Technology"].allocation_pct.quantize(Decimal("0.01")) == Decimal("66.67")
        assert by_sector["Healthcare"].allocation_pct.quantize(Decimal("0.01")) == Decimal("33.33")

    async def test_multiple_holdings_in_the_same_sector_sum_correctly(self) -> None:
        portfolio = _make_portfolio()
        other_tech = InstrumentId(uuid.uuid4())
        portfolio.apply_transaction(_make_buy(portfolio.id, TECH_INSTRUMENT, "10", "100"))
        portfolio.apply_transaction(_make_buy(portfolio.id, other_tech, "5", "100"))

        price_provider = FakePriceProvider(
            {str(TECH_INSTRUMENT): Decimal("100"), str(other_tech): Decimal("100")}
        )
        calc_service = PortfolioCalculationService(price_provider, FakeTransactionRepository([]))
        summary = await calc_service.compute_summary(portfolio)

        instrument_repo = FakeInstrumentRepository(
            {
                str(TECH_INSTRUMENT): _instrument(TECH_INSTRUMENT, "TECH", "Technology"),
                str(other_tech): _instrument(other_tech, "TECH2", "Technology"),
            }
        )

        allocation = await compute_sector_allocation(summary, instrument_repo)  # type: ignore[arg-type]

        assert len(allocation) == 1
        assert allocation[0].sector == "Technology"
        assert allocation[0].market_value.amount == Decimal("1500")
        assert allocation[0].allocation_pct == Decimal("100")

    async def test_a_holding_with_no_sector_data_is_grouped_under_unknown(self) -> None:
        portfolio = _make_portfolio()
        portfolio.apply_transaction(_make_buy(portfolio.id, UNKNOWN_SECTOR_INSTRUMENT, "10", "100"))

        price_provider = FakePriceProvider({str(UNKNOWN_SECTOR_INSTRUMENT): Decimal("100")})
        calc_service = PortfolioCalculationService(price_provider, FakeTransactionRepository([]))
        summary = await calc_service.compute_summary(portfolio)

        instrument_repo = FakeInstrumentRepository(
            {str(UNKNOWN_SECTOR_INSTRUMENT): _instrument(UNKNOWN_SECTOR_INSTRUMENT, "XYZ", None)}
        )

        allocation = await compute_sector_allocation(summary, instrument_repo)  # type: ignore[arg-type]

        assert len(allocation) == 1
        assert allocation[0].sector == "Unknown"
        assert allocation[0].allocation_pct == Decimal("100")

    async def test_returns_empty_tuple_for_a_portfolio_with_no_priced_holdings(self) -> None:
        portfolio = _make_portfolio()

        price_provider = FakePriceProvider({})
        calc_service = PortfolioCalculationService(price_provider, FakeTransactionRepository([]))
        summary = await calc_service.compute_summary(portfolio)

        instrument_repo = FakeInstrumentRepository({})
        allocation = await compute_sector_allocation(summary, instrument_repo)  # type: ignore[arg-type]

        assert allocation == ()
