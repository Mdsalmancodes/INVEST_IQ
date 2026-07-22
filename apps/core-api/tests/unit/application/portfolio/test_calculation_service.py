"""Unit tests for PortfolioCalculationService — the highest-priority tests
in Phase 3 per the founder's explicit instruction, since every one of these
calculations feeds the Portfolio Dashboard's headline numbers directly."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.application.portfolio.calculation_service import PortfolioCalculationService
from src.domain.portfolio.entities import Portfolio, Transaction, TransactionType
from src.domain.portfolio.repositories import PageResult, TransactionFilter
from src.domain.portfolio.value_objects import (
    InstrumentId,
    Money,
    PortfolioId,
    Quantity,
    TransactionId,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
INSTRUMENT_A = InstrumentId(uuid.uuid4())
INSTRUMENT_B = InstrumentId(uuid.uuid4())


class FakePriceProvider:
    def __init__(
        self,
        current_prices: dict[str, Decimal] | None = None,
        previous_closes: dict[str, Decimal] | None = None,
    ) -> None:
        self._current_prices = current_prices or {}
        self._previous_closes = previous_closes or {}

    async def get_current_price(self, instrument_id: InstrumentId) -> Money | None:
        raw = self._current_prices.get(str(instrument_id))
        return Money(raw) if raw is not None else None

    async def get_previous_close(self, instrument_id: InstrumentId) -> Money | None:
        raw = self._previous_closes.get(str(instrument_id))
        return Money(raw) if raw is not None else None


class FakeTransactionRepository:
    def __init__(self, transactions: list[Transaction] | None = None) -> None:
        self._transactions = transactions or []

    async def save(self, transaction: Transaction) -> None:
        self._transactions.append(transaction)

    async def get_by_id(self, transaction_id: TransactionId) -> Transaction | None:
        for tx in self._transactions:
            if tx.id == transaction_id:
                return tx
        return None

    async def list_for_portfolio(
        self, portfolio_id: PortfolioId, filters: TransactionFilter
    ) -> PageResult:
        matching = [tx for tx in self._transactions if tx.portfolio_id == portfolio_id]
        return PageResult(
            items=tuple(matching), total_count=len(matching), page=1, page_size=len(matching) or 20
        )

    async def list_all_for_portfolio_unpaginated(
        self, portfolio_id: PortfolioId
    ) -> tuple[Transaction, ...]:
        return tuple(tx for tx in self._transactions if tx.portfolio_id == portfolio_id)


def make_portfolio() -> Portfolio:
    return Portfolio(
        id=PortfolioId.new(),
        user_id="user-1",
        name="My Portfolio",
        base_currency="USD",
        is_paper=False,
        created_at=NOW,
        updated_at=NOW,
    )


def make_buy(
    portfolio_id: PortfolioId,
    instrument_id: InstrumentId,
    quantity: str,
    price: str,
    fees: str = "0",
) -> Transaction:
    return Transaction(
        id=TransactionId.new(),
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        type=TransactionType.BUY,
        quantity=Quantity(Decimal(quantity)),
        price=Money(Decimal(price)),
        fees=Money(Decimal(fees)),
        split_ratio=None,
        related_portfolio_id=None,
        cash_amount=None,
        executed_at=NOW,
        created_at=NOW,
    )


def make_sell(
    portfolio_id: PortfolioId,
    instrument_id: InstrumentId,
    quantity: str,
    price: str,
    fees: str = "0",
) -> Transaction:
    return Transaction(
        id=TransactionId.new(),
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        type=TransactionType.SELL,
        quantity=Quantity(Decimal(quantity)),
        price=Money(Decimal(price)),
        fees=Money(Decimal(fees)),
        split_ratio=None,
        related_portfolio_id=None,
        cash_amount=None,
        executed_at=NOW,
        created_at=NOW,
    )


def make_dividend(
    portfolio_id: PortfolioId, instrument_id: InstrumentId, per_share: str, quantity: str
) -> Transaction:
    return Transaction(
        id=TransactionId.new(),
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        type=TransactionType.DIVIDEND,
        quantity=Quantity(Decimal(quantity)),
        price=Money(Decimal(per_share)),
        fees=Money.zero(),
        split_ratio=None,
        related_portfolio_id=None,
        cash_amount=None,
        executed_at=NOW,
        created_at=NOW,
    )


@pytest.mark.asyncio
class TestTotalInvestmentAndCurrentValue:
    async def test_single_holding(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("120")}),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)

        assert summary.total_investment.amount == Decimal("1000.00000000")
        assert summary.current_value.amount == Decimal("1200.00000000")

    async def test_multiple_holdings_sum_correctly(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_B, "5", "50"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(
                current_prices={str(INSTRUMENT_A): Decimal("110"), str(INSTRUMENT_B): Decimal("60")}
            ),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)

        # total investment: 10*100 + 5*50 = 1250
        assert summary.total_investment.amount == Decimal("1250.00000000")
        # current value: 10*110 + 5*60 = 1400
        assert summary.current_value.amount == Decimal("1400.00000000")

    async def test_holding_with_missing_price_excluded_from_totals(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_B, "5", "50"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("110")}),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)

        # total_investment still includes BOTH holdings (cost basis doesn't need a live price)
        assert summary.total_investment.amount == Decimal("1250.00000000")
        # current_value only includes the priced holding
        assert summary.current_value.amount == Decimal("1100.00000000")
        assert str(INSTRUMENT_B) in summary.holdings_missing_price

    async def test_fully_sold_holding_excluded_entirely(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_sell(portfolio.id, INSTRUMENT_A, "10", "150"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("150")}),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)

        assert summary.total_investment.amount == Decimal("0E-8")
        assert summary.current_value.amount == Decimal("0E-8")
        assert len(summary.holdings) == 0


@pytest.mark.asyncio
class TestProfitLossCalculations:
    async def test_profit_loss_positive(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("120")}),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)

        assert summary.profit_loss.amount == Decimal("200.00000000")
        assert summary.profit_loss_pct == Decimal("20")

    async def test_profit_loss_negative(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("80")}),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)

        assert summary.profit_loss.amount == Decimal("-200.00000000")
        assert summary.profit_loss_pct == Decimal("-20")

    async def test_profit_loss_pct_zero_when_no_investment(self) -> None:
        portfolio = make_portfolio()
        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)
        assert summary.profit_loss_pct == Decimal("0")


@pytest.mark.asyncio
class TestAverageBuyPrice:
    async def test_reflected_in_holding_summary(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "200"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("150")}),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)

        assert len(summary.holdings) == 1
        assert summary.holdings[0].average_buy_price.amount == Decimal("150.00000000")


@pytest.mark.asyncio
class TestRealizedGain:
    async def test_no_sells_means_zero_realized_gain(self) -> None:
        portfolio = make_portfolio()
        buy = make_buy(portfolio.id, INSTRUMENT_A, "10", "100")
        portfolio.apply_transaction(buy)
        repo = FakeTransactionRepository([buy])

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("150")}),
            transaction_repository=repo,
        )
        summary = await service.compute_summary(portfolio)
        assert summary.realized_gain.amount == Decimal("0.00000000")

    async def test_single_sell_computes_gain(self) -> None:
        portfolio = make_portfolio()
        buy = make_buy(portfolio.id, INSTRUMENT_A, "10", "100")
        sell = make_sell(portfolio.id, INSTRUMENT_A, "4", "150")
        portfolio.apply_transaction(buy)
        portfolio.apply_transaction(sell)
        repo = FakeTransactionRepository([buy, sell])

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("150")}),
            transaction_repository=repo,
        )
        summary = await service.compute_summary(portfolio)
        # (150-100)*4 = 200
        assert summary.realized_gain.amount == Decimal("200.00000000")

    async def test_multiple_sells_across_lots_accumulate(self) -> None:
        portfolio = make_portfolio()
        buy1 = make_buy(portfolio.id, INSTRUMENT_A, "10", "100")
        buy2 = make_buy(portfolio.id, INSTRUMENT_A, "10", "200")
        # weighted avg after both buys = 150; sell 5 shares at 180
        sell = make_sell(portfolio.id, INSTRUMENT_A, "5", "180")
        for tx in (buy1, buy2, sell):
            portfolio.apply_transaction(tx)
        repo = FakeTransactionRepository([buy1, buy2, sell])

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("180")}),
            transaction_repository=repo,
        )
        summary = await service.compute_summary(portfolio)
        # (180-150)*5 = 150
        assert summary.realized_gain.amount == Decimal("150.00000000")

    async def test_sell_with_fees_reduces_gain(self) -> None:
        portfolio = make_portfolio()
        buy = make_buy(portfolio.id, INSTRUMENT_A, "10", "100")
        sell = make_sell(portfolio.id, INSTRUMENT_A, "10", "150", fees="50")
        portfolio.apply_transaction(buy)
        portfolio.apply_transaction(sell)
        repo = FakeTransactionRepository([buy, sell])

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(),
            transaction_repository=repo,
        )
        summary = await service.compute_summary(portfolio)
        # proceeds = 1500-50=1450; cost=1000; gain=450
        assert summary.realized_gain.amount == Decimal("450.00000000")


@pytest.mark.asyncio
class TestUnrealizedGain:
    async def test_matches_sum_of_per_holding_unrealized_gains(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_B, "5", "50"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(
                current_prices={str(INSTRUMENT_A): Decimal("120"), str(INSTRUMENT_B): Decimal("40")}
            ),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)
        # A: (120-100)*10=200; B: (40-50)*5=-50; total=150
        assert summary.unrealized_gain.amount == Decimal("150.00000000")


@pytest.mark.asyncio
class TestDividendIncome:
    async def test_single_dividend(self) -> None:
        portfolio = make_portfolio()
        buy = make_buy(portfolio.id, INSTRUMENT_A, "10", "100")
        dividend = make_dividend(portfolio.id, INSTRUMENT_A, per_share="2", quantity="10")
        portfolio.apply_transaction(buy)
        portfolio.apply_transaction(dividend)
        repo = FakeTransactionRepository([buy, dividend])

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("100")}),
            transaction_repository=repo,
        )
        summary = await service.compute_summary(portfolio)
        assert summary.dividend_income.amount == Decimal("20.00000000")

    async def test_multiple_dividends_accumulate(self) -> None:
        portfolio = make_portfolio()
        buy = make_buy(portfolio.id, INSTRUMENT_A, "10", "100")
        div1 = make_dividend(portfolio.id, INSTRUMENT_A, per_share="2", quantity="10")
        div2 = make_dividend(portfolio.id, INSTRUMENT_A, per_share="3", quantity="10")
        portfolio.apply_transaction(buy)
        repo = FakeTransactionRepository([buy, div1, div2])

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("100")}),
            transaction_repository=repo,
        )
        summary = await service.compute_summary(portfolio)
        assert summary.dividend_income.amount == Decimal("50.00000000")

    async def test_no_dividends_means_zero(self) -> None:
        portfolio = make_portfolio()
        buy = make_buy(portfolio.id, INSTRUMENT_A, "10", "100")
        portfolio.apply_transaction(buy)
        repo = FakeTransactionRepository([buy])

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("100")}),
            transaction_repository=repo,
        )
        summary = await service.compute_summary(portfolio)
        assert summary.dividend_income.amount == Decimal("0.00000000")


@pytest.mark.asyncio
class TestAllocationPercentage:
    async def test_two_holdings_split_evenly(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_B, "10", "100"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(
                current_prices={
                    str(INSTRUMENT_A): Decimal("100"),
                    str(INSTRUMENT_B): Decimal("100"),
                }
            ),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)

        allocations = {str(h.instrument_id): h.allocation_pct for h in summary.holdings}
        assert allocations[str(INSTRUMENT_A)] == Decimal("50")
        assert allocations[str(INSTRUMENT_B)] == Decimal("50")

    async def test_uneven_allocation(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))  # value 1000
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_B, "10", "300"))  # value 3000

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(
                current_prices={
                    str(INSTRUMENT_A): Decimal("100"),
                    str(INSTRUMENT_B): Decimal("300"),
                }
            ),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)

        allocations = {str(h.instrument_id): h.allocation_pct for h in summary.holdings}
        assert allocations[str(INSTRUMENT_A)] == Decimal("25")
        assert allocations[str(INSTRUMENT_B)] == Decimal("75")

    async def test_missing_price_holding_has_none_allocation(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_B, "10", "100"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("100")}),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)

        by_id = {str(h.instrument_id): h for h in summary.holdings}
        assert by_id[str(INSTRUMENT_A)].allocation_pct == Decimal("100")
        assert by_id[str(INSTRUMENT_B)].allocation_pct is None


@pytest.mark.asyncio
class TestDailyGainLoss:
    async def test_positive_daily_gain(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(
                current_prices={str(INSTRUMENT_A): Decimal("105")},
                previous_closes={str(INSTRUMENT_A): Decimal("100")},
            ),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)
        # (105-100)*10 = 50
        assert summary.daily_gain.amount == Decimal("50.00000000")

    async def test_negative_daily_gain(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(
                current_prices={str(INSTRUMENT_A): Decimal("95")},
                previous_closes={str(INSTRUMENT_A): Decimal("100")},
            ),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)
        assert summary.daily_gain.amount == Decimal("-50.00000000")

    async def test_missing_previous_close_excludes_holding_from_daily_gain(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(current_prices={str(INSTRUMENT_A): Decimal("105")}),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)
        assert summary.daily_gain.amount == Decimal("0.00000000")
        assert summary.holdings[0].daily_gain is None

    async def test_multiple_holdings_daily_gain_sums(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_B, "5", "50"))

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(
                current_prices={
                    str(INSTRUMENT_A): Decimal("105"),
                    str(INSTRUMENT_B): Decimal("48"),
                },
                previous_closes={
                    str(INSTRUMENT_A): Decimal("100"),
                    str(INSTRUMENT_B): Decimal("50"),
                },
            ),
            transaction_repository=FakeTransactionRepository(),
        )
        summary = await service.compute_summary(portfolio)
        # A: (105-100)*10=50; B: (48-50)*5=-10; total=40
        assert summary.daily_gain.amount == Decimal("40.00000000")


@pytest.mark.asyncio
class TestSplitAndTransferInteractionWithCalculations:
    async def test_realized_gain_after_split_uses_adjusted_cost_basis(self) -> None:
        portfolio = make_portfolio()
        buy = make_buy(portfolio.id, INSTRUMENT_A, "10", "100")
        split = Transaction(
            id=TransactionId.new(),
            portfolio_id=portfolio.id,
            instrument_id=INSTRUMENT_A,
            type=TransactionType.SPLIT,
            quantity=None,
            price=None,
            fees=Money.zero(),
            split_ratio=2.0,
            related_portfolio_id=None,
            cash_amount=None,
            executed_at=NOW,
            created_at=NOW,
        )
        # after 2:1 split: 20 shares @ avg cost 50
        sell = make_sell(portfolio.id, INSTRUMENT_A, "20", "60")
        for tx in (buy, split, sell):
            portfolio.apply_transaction(tx)
        repo = FakeTransactionRepository([buy, split, sell])

        service = PortfolioCalculationService(
            price_provider=FakePriceProvider(),
            transaction_repository=repo,
        )
        summary = await service.compute_summary(portfolio)
        # (60-50)*20 = 200
        assert summary.realized_gain.amount == Decimal("200.00000000")
