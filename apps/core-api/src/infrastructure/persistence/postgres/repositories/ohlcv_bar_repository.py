"""SqlAlchemyOhlcvBarRepository — implements
src.domain.market_data.repositories.OhlcvBarRepository."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.market_data.entities import OhlcvBar
from src.domain.market_data.repositories import OhlcvBarQuery
from src.domain.market_data.value_objects import InstrumentId, Interval
from src.infrastructure.persistence.postgres.market_data_models import OhlcvBarModel
from src.infrastructure.persistence.postgres.repositories.market_data_mappers import (
    ohlcv_bar_to_domain,
    ohlcv_bar_to_model,
)


class SqlAlchemyOhlcvBarRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, bar: OhlcvBar) -> None:
        existing = await self._session.get(
            OhlcvBarModel, (bar.instrument_id.value, bar.interval.value, bar.bar_time)
        )
        model = ohlcv_bar_to_model(bar, existing=existing)
        if existing is None:
            self._session.add(model)
        await self._session.flush()

    async def save_many(self, bars: tuple[OhlcvBar, ...]) -> None:
        if not bars:
            return
        # Upsert via Postgres INSERT ... ON CONFLICT DO UPDATE, keyed by
        # the (instrument_id, interval, bar_time) primary key — this is
        # the dedupe rule from Document 5 §11.2 stage 2 ("a reconnected
        # stream replaying the last few ticks must not double-count").
        # Not literally Postgres COPY (Document 5 §11.3's stated
        # performance optimization for very large historical ranges) —
        # a disclosed simplification; ON CONFLICT DO UPDATE is correct and
        # reasonably performant for the batch sizes a single-symbol
        # backfill produces (a few thousand rows), COPY's throughput
        # advantage matters at a scale (bulk multi-symbol backfill) this
        # phase's Celery task does not yet attempt.
        values = [
            {
                "instrument_id": bar.instrument_id.value,
                "interval": bar.interval.value,
                "bar_time": bar.bar_time,
                "open": bar.open.amount,
                "high": bar.high.amount,
                "low": bar.low.amount,
                "close": bar.close.amount,
                "adjusted_close": bar.adjusted_close.amount,
                "volume": bar.volume,
                "is_closed": bar.is_closed,
                "source": bar.source,
                "created_at": bar.created_at,
            }
            for bar in bars
        ]
        stmt = pg_insert(OhlcvBarModel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["instrument_id", "interval", "bar_time"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "adjusted_close": stmt.excluded.adjusted_close,
                "volume": stmt.excluded.volume,
                "is_closed": stmt.excluded.is_closed,
                "source": stmt.excluded.source,
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def query(self, query: OhlcvBarQuery) -> tuple[OhlcvBar, ...]:
        stmt = select(OhlcvBarModel).where(
            OhlcvBarModel.instrument_id == query.instrument_id.value,
            OhlcvBarModel.interval == query.interval.value,
        )
        if query.start is not None:
            stmt = stmt.where(OhlcvBarModel.bar_time >= query.start)
        if query.end is not None:
            stmt = stmt.where(OhlcvBarModel.bar_time <= query.end)
        stmt = stmt.order_by(OhlcvBarModel.bar_time.asc())
        if query.limit is not None:
            stmt = stmt.limit(query.limit)

        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return tuple(ohlcv_bar_to_domain(model) for model in models)

    async def get_latest_closed_bar(
        self, instrument_id: InstrumentId, interval: Interval
    ) -> OhlcvBar | None:
        stmt = (
            select(OhlcvBarModel)
            .where(
                OhlcvBarModel.instrument_id == instrument_id.value,
                OhlcvBarModel.interval == interval.value,
                OhlcvBarModel.is_closed.is_(True),
            )
            .order_by(OhlcvBarModel.bar_time.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return ohlcv_bar_to_domain(model) if model is not None else None

    async def apply_adjustment_factor_before_date(
        self, instrument_id: InstrumentId, before: date, factor: Decimal
    ) -> int:
        stmt = (
            update(OhlcvBarModel)
            .where(
                OhlcvBarModel.instrument_id == instrument_id.value,
                OhlcvBarModel.bar_time < before,
            )
            .values(adjusted_close=OhlcvBarModel.adjusted_close * factor)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        # AsyncSession.execute() is typed to return the generic Result[Any]
        # (no rowcount attribute in that stub), but a real UPDATE statement
        # actually returns a CursorResult at runtime, which does have
        # rowcount — a documented SQLAlchemy 2 async typing gap, not a bug
        # in this code. Scoped ignore, not a blanket suppression.
        return int(result.rowcount)  # type: ignore[attr-defined]
