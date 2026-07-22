"""PortfolioCalculationService — computes all Phase 3 financial metrics.

Per the founder's explicit Phase 3 requirement list:
- Total Investment      (sum of cost basis across all current holdings)
- Current Value         (sum of market value across all current holdings)
- Profit/Loss           (Current Value - Total Investment)
- Profit %              (P/L / Total Investment * 100)
- Average Buy Price     (per holding: Holding.average_cost, exposed directly)
- Realized Gain         (sum of gains from all `sell` transactions to date)
- Unrealized Gain       (sum of Holding.unrealized_gain across current holdings)
- Dividend Income       (sum of all `dividend` transaction amounts to date)
- Allocation %          (per holding: holding market value / Current Value * 100)
- Daily Gain/Loss       ((current_price - previous_close) * quantity, summed)

All monetary results are Money (Decimal-backed) — Document 3 §3.4 rule #2.
Holdings with no available current price are excluded from price-dependent
aggregates (Current Value, Unrealized Gain, Daily Gain/Loss, Allocation %)
and reported separately as `holdings_missing_price`, rather than silently
treating a missing price as zero (which would corrupt every downstream sum).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.application.portfolio.price_provider import PriceProvider
from src.domain.portfolio.entities import Portfolio, TransactionType
from src.domain.portfolio.repositories import TransactionRepository
from src.domain.portfolio.value_objects import InstrumentId, Money


@dataclass(frozen=True, slots=True)
class HoldingSummary:
    instrument_id: InstrumentId
    quantity: Decimal
    average_buy_price: Money
    current_price: Money | None
    market_value: Money | None
    unrealized_gain: Money | None
    allocation_pct: Decimal | None
    daily_gain: Money | None


@dataclass(frozen=True, slots=True)
class PortfolioSummary:
    portfolio_id: str
    total_investment: Money
    current_value: Money
    profit_loss: Money
    profit_loss_pct: Decimal
    realized_gain: Money
    unrealized_gain: Money
    dividend_income: Money
    daily_gain: Money
    holdings: tuple[HoldingSummary, ...]
    holdings_missing_price: tuple[str, ...]  # instrument ids excluded from price-dependent totals


class PortfolioCalculationService:
    def __init__(
        self, price_provider: PriceProvider, transaction_repository: TransactionRepository
    ) -> None:
        self._price_provider = price_provider
        self._transaction_repository = transaction_repository

    async def compute_summary(self, portfolio: Portfolio) -> PortfolioSummary:
        holding_summaries: list[HoldingSummary] = []
        holdings_missing_price: list[str] = []

        total_investment = Money.zero()
        current_value = Money.zero()
        unrealized_gain = Money.zero()
        daily_gain = Money.zero()

        # First pass: fetch prices and compute per-holding values (needed
        # before allocation % can be computed, since it depends on the
        # portfolio-wide Current Value total).
        priced_holdings: list[tuple[InstrumentId, Decimal, Money, Money, Money]] = []
        for holding in portfolio.holdings.values():
            if holding.quantity.is_zero():
                continue  # a fully-sold-out holding contributes nothing to any total
            total_investment = total_investment + holding.total_cost_basis()

            current_price = await self._price_provider.get_current_price(holding.instrument_id)
            if current_price is None:
                holdings_missing_price.append(str(holding.instrument_id))
                holding_summaries.append(
                    HoldingSummary(
                        instrument_id=holding.instrument_id,
                        quantity=holding.quantity.value,
                        average_buy_price=holding.average_cost,
                        current_price=None,
                        market_value=None,
                        unrealized_gain=None,
                        allocation_pct=None,
                        daily_gain=None,
                    )
                )
                continue

            market_value = holding.market_value(current_price)
            holding_unrealized_gain = holding.unrealized_gain(current_price)
            current_value = current_value + market_value
            unrealized_gain = unrealized_gain + holding_unrealized_gain

            previous_close = await self._price_provider.get_previous_close(holding.instrument_id)
            holding_daily_gain = Money.zero()
            if previous_close is not None:
                price_delta = current_price - previous_close
                holding_daily_gain = price_delta * holding.quantity.value
                daily_gain = daily_gain + holding_daily_gain

            priced_holdings.append(
                (
                    holding.instrument_id,
                    holding.quantity.value,
                    holding.average_cost,
                    market_value,
                    holding_unrealized_gain,
                )
            )
            holding_summaries.append(
                HoldingSummary(
                    instrument_id=holding.instrument_id,
                    quantity=holding.quantity.value,
                    average_buy_price=holding.average_cost,
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_gain=holding_unrealized_gain,
                    allocation_pct=None,  # filled in second pass below
                    daily_gain=holding_daily_gain if previous_close is not None else None,
                )
            )

        # Second pass: allocation % requires the final Current Value total.
        final_summaries: list[HoldingSummary] = []
        for summary in holding_summaries:
            if summary.market_value is None or current_value.amount == Decimal("0"):
                final_summaries.append(summary)
                continue
            allocation_pct = (summary.market_value.amount / current_value.amount) * Decimal("100")
            final_summaries.append(
                HoldingSummary(
                    instrument_id=summary.instrument_id,
                    quantity=summary.quantity,
                    average_buy_price=summary.average_buy_price,
                    current_price=summary.current_price,
                    market_value=summary.market_value,
                    unrealized_gain=summary.unrealized_gain,
                    allocation_pct=allocation_pct,
                    daily_gain=summary.daily_gain,
                )
            )

        realized_gain = await self._compute_realized_gain(portfolio)
        dividend_income = await self._compute_dividend_income(portfolio)

        profit_loss = current_value - total_investment
        profit_loss_pct = (
            (profit_loss.amount / total_investment.amount) * Decimal("100")
            if total_investment.amount != Decimal("0")
            else Decimal("0")
        )

        return PortfolioSummary(
            portfolio_id=str(portfolio.id),
            total_investment=total_investment,
            current_value=current_value,
            profit_loss=profit_loss,
            profit_loss_pct=profit_loss_pct,
            realized_gain=realized_gain,
            unrealized_gain=unrealized_gain,
            dividend_income=dividend_income,
            daily_gain=daily_gain,
            holdings=tuple(final_summaries),
            holdings_missing_price=tuple(holdings_missing_price),
        )

    async def _compute_realized_gain(self, portfolio: Portfolio) -> Money:
        transactions = await self._transaction_repository.list_all_for_portfolio_unpaginated(
            portfolio.id
        )
        total = Money.zero()
        # Realized gain must be recomputed from full history via a
        # replay-based average-cost simulation, NOT read off Holding state
        # (which only reflects the CURRENT position, having already
        # discarded the cost basis of shares that were sold). We replay
        # buy/sell/transfer/split against per-instrument running cost
        # basis, mirroring exactly what Portfolio.apply_transaction does,
        # to compute the gain realized at each sell.
        running_qty: dict[str, Decimal] = {}
        running_avg_cost: dict[str, Decimal] = {}
        for tx in transactions:
            if tx.instrument_id is None:
                continue
            key = str(tx.instrument_id)
            if tx.type == TransactionType.BUY:
                assert tx.quantity is not None and tx.price is not None
                existing_qty = running_qty.get(key, Decimal("0"))
                existing_avg = running_avg_cost.get(key, Decimal("0"))
                new_qty = existing_qty + tx.quantity.value
                new_cost = (
                    (existing_qty * existing_avg)
                    + (tx.quantity.value * tx.price.amount)
                    + tx.fees.amount
                )
                running_qty[key] = new_qty
                running_avg_cost[key] = (
                    new_cost / new_qty if new_qty != Decimal("0") else Decimal("0")
                )
            elif tx.type == TransactionType.TRANSFER_IN:
                assert tx.quantity is not None and tx.price is not None
                existing_qty = running_qty.get(key, Decimal("0"))
                existing_avg = running_avg_cost.get(key, Decimal("0"))
                new_qty = existing_qty + tx.quantity.value
                new_cost = (existing_qty * existing_avg) + (tx.quantity.value * tx.price.amount)
                running_qty[key] = new_qty
                running_avg_cost[key] = (
                    new_cost / new_qty if new_qty != Decimal("0") else Decimal("0")
                )
            elif tx.type == TransactionType.SELL:
                assert tx.quantity is not None and tx.price is not None
                avg_cost = running_avg_cost.get(key, Decimal("0"))
                proceeds = (tx.quantity.value * tx.price.amount) - tx.fees.amount
                cost_of_sold = tx.quantity.value * avg_cost
                total = total + Money(proceeds - cost_of_sold)
                running_qty[key] = running_qty.get(key, Decimal("0")) - tx.quantity.value
            elif tx.type == TransactionType.TRANSFER_OUT:
                assert tx.quantity is not None
                running_qty[key] = running_qty.get(key, Decimal("0")) - tx.quantity.value
            elif tx.type == TransactionType.SPLIT:
                assert tx.split_ratio is not None
                ratio = Decimal(str(tx.split_ratio))
                existing_qty = running_qty.get(key, Decimal("0"))
                existing_avg = running_avg_cost.get(key, Decimal("0"))
                running_qty[key] = existing_qty * ratio
                running_avg_cost[key] = (
                    existing_avg / ratio if ratio != Decimal("0") else existing_avg
                )
        return total

    async def _compute_dividend_income(self, portfolio: Portfolio) -> Money:
        transactions = await self._transaction_repository.list_all_for_portfolio_unpaginated(
            portfolio.id
        )
        total = Money.zero()
        for tx in transactions:
            if (
                tx.type == TransactionType.DIVIDEND
                and tx.price is not None
                and tx.quantity is not None
            ):
                # price = per-share dividend amount, quantity = shares held
                # at the time (Transaction._validate enforces both are set).
                total = total + (tx.price * tx.quantity.value)
        return total
