"""Domain <-> ORM mapping functions for the market_data bounded context.

Mirrors src/infrastructure/persistence/postgres/repositories/
portfolio_mappers.py's pattern — pure functions, no side effects.
"""

from __future__ import annotations

from src.domain.market_data.entities import (
    AssetType,
    CorporateAction,
    CorporateActionType,
    Instrument,
    OhlcvBar,
)
from src.domain.market_data.value_objects import CorporateActionId, InstrumentId, Interval, Price
from src.infrastructure.persistence.postgres.market_data_models import (
    CorporateActionModel,
    OhlcvBarModel,
)
from src.infrastructure.persistence.postgres.portfolio_models import InstrumentModel


def instrument_to_domain(model: InstrumentModel) -> Instrument:
    return Instrument(
        id=InstrumentId(model.id),
        symbol=model.symbol,
        exchange=model.exchange,
        name=model.name,
        asset_type=AssetType(model.asset_type),
        currency=model.currency,
        sector=model.sector,
        industry=model.industry,
        ipo_date=model.ipo_date,
        is_active=model.is_active,
        created_at=model.created_at,
    )


def instrument_to_model(
    instrument: Instrument, existing: InstrumentModel | None
) -> InstrumentModel:
    model = existing if existing is not None else InstrumentModel(id=instrument.id.value)
    model.symbol = instrument.symbol
    model.exchange = instrument.exchange
    model.name = instrument.name
    model.asset_type = instrument.asset_type.value
    model.currency = instrument.currency
    model.sector = instrument.sector
    model.industry = instrument.industry
    model.ipo_date = instrument.ipo_date
    model.is_active = instrument.is_active
    model.created_at = instrument.created_at
    return model


def ohlcv_bar_to_domain(model: OhlcvBarModel) -> OhlcvBar:
    return OhlcvBar(
        instrument_id=InstrumentId(model.instrument_id),
        interval=Interval.from_string(model.interval),
        bar_time=model.bar_time,
        open=Price(model.open),
        high=Price(model.high),
        low=Price(model.low),
        close=Price(model.close),
        adjusted_close=Price(model.adjusted_close),
        volume=model.volume,
        is_closed=model.is_closed,
        source=model.source,
        created_at=model.created_at,
    )


def ohlcv_bar_to_model(bar: OhlcvBar, existing: OhlcvBarModel | None) -> OhlcvBarModel:
    model = (
        existing
        if existing is not None
        else OhlcvBarModel(
            instrument_id=bar.instrument_id.value,
            interval=bar.interval.value,
            bar_time=bar.bar_time,
        )
    )
    model.open = bar.open.amount
    model.high = bar.high.amount
    model.low = bar.low.amount
    model.close = bar.close.amount
    model.adjusted_close = bar.adjusted_close.amount
    model.volume = bar.volume
    model.is_closed = bar.is_closed
    model.source = bar.source
    model.created_at = bar.created_at
    return model


def corporate_action_to_domain(model: CorporateActionModel) -> CorporateAction:
    return CorporateAction(
        id=CorporateActionId(model.id),
        instrument_id=InstrumentId(model.instrument_id),
        action_type=CorporateActionType(model.action_type),
        ratio=model.ratio,
        cash_amount=Price(model.cash_amount) if model.cash_amount is not None else None,
        ex_date=model.ex_date,
        announced_at=model.announced_at,
        created_at=model.created_at,
    )


def corporate_action_to_model(action: CorporateAction) -> CorporateActionModel:
    # Corporate actions are append-only in practice (a real-world split/
    # dividend is a historical fact, never edited) — always a fresh insert,
    # matching Transaction's append-only pattern in the portfolio context.
    return CorporateActionModel(
        id=action.id.value,
        instrument_id=action.instrument_id.value,
        action_type=action.action_type.value,
        ratio=action.ratio,
        cash_amount=action.cash_amount.amount if action.cash_amount is not None else None,
        ex_date=action.ex_date,
        announced_at=action.announced_at,
        created_at=action.created_at,
    )
