"""Domain <-> ORM mapping functions for the portfolio bounded context.

Mirrors the pattern in
src/infrastructure/persistence/postgres/repositories/mappers.py (auth
context) — pure functions, no side effects, isolate the domain layer from
SQLAlchemy model shape.
"""

from __future__ import annotations

from decimal import Decimal

from src.domain.portfolio.entities import Holding, Portfolio, Transaction, TransactionType
from src.domain.portfolio.value_objects import (
    HoldingId,
    InstrumentId,
    Money,
    PortfolioId,
    Quantity,
    TransactionId,
)
from src.infrastructure.persistence.postgres.portfolio_models import (
    HoldingModel,
    PortfolioModel,
    TransactionModel,
)


def holding_to_domain(model: HoldingModel) -> Holding:
    return Holding(
        id=HoldingId(model.id),
        portfolio_id=PortfolioId(model.portfolio_id),
        instrument_id=InstrumentId(model.instrument_id),
        quantity=Quantity(model.quantity),
        average_cost=Money(model.average_cost),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def holding_to_model(holding: Holding, existing: HoldingModel | None) -> HoldingModel:
    model = existing if existing is not None else HoldingModel(id=holding.id.value)
    model.portfolio_id = holding.portfolio_id.value
    model.instrument_id = holding.instrument_id.value
    model.quantity = holding.quantity.value
    model.average_cost = holding.average_cost.amount
    model.created_at = holding.created_at
    model.updated_at = holding.updated_at
    return model


def portfolio_to_domain(model: PortfolioModel) -> Portfolio:
    portfolio = Portfolio(
        id=PortfolioId(model.id),
        user_id=str(model.user_id),
        name=model.name,
        base_currency=model.base_currency,
        is_paper=model.is_paper,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
    for holding_model in model.holdings:
        holding = holding_to_domain(holding_model)
        portfolio.holdings[str(holding.instrument_id)] = holding
    return portfolio


def portfolio_to_model(portfolio: Portfolio, existing: PortfolioModel | None) -> PortfolioModel:
    model = existing if existing is not None else PortfolioModel(id=portfolio.id.value)
    model.user_id = portfolio.user_id  # type: ignore[assignment]  # str -> UUID column, driver-coerced
    model.name = portfolio.name
    model.base_currency = portfolio.base_currency
    model.is_paper = portfolio.is_paper
    model.created_at = portfolio.created_at
    model.updated_at = portfolio.updated_at
    return model


def transaction_to_domain(model: TransactionModel) -> Transaction:
    return Transaction(
        id=TransactionId(model.id),
        portfolio_id=PortfolioId(model.portfolio_id),
        instrument_id=InstrumentId(model.instrument_id) if model.instrument_id else None,
        type=TransactionType(model.type),
        quantity=Quantity(model.quantity) if model.quantity is not None else None,
        price=Money(model.price) if model.price is not None else None,
        fees=Money(model.fees),
        split_ratio=float(model.split_ratio) if model.split_ratio is not None else None,
        related_portfolio_id=(
            PortfolioId(model.related_portfolio_id) if model.related_portfolio_id else None
        ),
        cash_amount=Money(model.cash_amount) if model.cash_amount is not None else None,
        executed_at=model.executed_at,
        created_at=model.created_at,
    )


def transaction_to_model(transaction: Transaction) -> TransactionModel:
    # Transactions are append-only (Document 3 §3.4) — always a fresh insert,
    # never an update-in-place, so this has no `existing` parameter.
    split_ratio_decimal: Decimal | None = (
        Decimal(str(transaction.split_ratio)) if transaction.split_ratio is not None else None
    )
    return TransactionModel(
        id=transaction.id.value,
        portfolio_id=transaction.portfolio_id.value,
        instrument_id=transaction.instrument_id.value if transaction.instrument_id else None,
        type=transaction.type.value,
        quantity=transaction.quantity.value if transaction.quantity is not None else None,
        price=transaction.price.amount if transaction.price is not None else None,
        fees=transaction.fees.amount,
        split_ratio=split_ratio_decimal,
        related_portfolio_id=(
            transaction.related_portfolio_id.value
            if transaction.related_portfolio_id is not None
            else None
        ),
        cash_amount=transaction.cash_amount.amount if transaction.cash_amount is not None else None,
        executed_at=transaction.executed_at,
        created_at=transaction.created_at,
    )
