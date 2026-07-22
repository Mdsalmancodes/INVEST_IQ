"""SQLAlchemy declarative models for the Market Data bounded context.

Per docs/architecture/03-backend-architecture-database-design.md §8.1
(ohlcv_bars, corporate_actions). `InstrumentModel` already exists in
portfolio_models.py (created in Phase 3 as a minimal FK-target subset of
this same frozen table) — not duplicated here.

These are infrastructure-layer concerns (Document 2 §4.1) — the domain
entities in src.domain.market_data.entities are the real business objects;
these ORM models exist only to persist them.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.postgres.models import Base

_NUMERIC_20_8 = Numeric(20, 8)


class OhlcvBarModel(Base):
    """Per Document 3 §8.1 `ohlcv_bars` table — "the highest write/read
    volume table in the platform." The frozen DDL specifies native Postgres
    RANGE partitioning by `bar_time` with a scheduled monthly
    partition-creation job; that maintenance job is NOT built in this
    phase (out of founder's explicit Phase 4 scope) — see
    docs/phase-4/verification-report.md for the disclosed simplification
    and upgrade path. The table itself is created as a normal
    (non-partitioned) table for now; switching to native partitioning
    later requires a migration but no application-code change, since all
    reads/writes already go through OhlcvBarRepository.
    """

    __tablename__ = "ohlcv_bars"
    __table_args__ = (
        CheckConstraint(
            "interval IN ('1min','5min','15min','1h','1d','1w')",
            name="ck_ohlcv_bars_interval",
        ),
        CheckConstraint("volume >= 0", name="ck_ohlcv_bars_volume_non_negative"),
        Index(
            "idx_ohlcv_bars_instrument_interval_time",
            "instrument_id",
            "interval",
            "bar_time",
        ),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id"), primary_key=True
    )
    interval: Mapped[str] = mapped_column(Text, primary_key=True)
    bar_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[Decimal] = mapped_column(_NUMERIC_20_8, nullable=False)
    high: Mapped[Decimal] = mapped_column(_NUMERIC_20_8, nullable=False)
    low: Mapped[Decimal] = mapped_column(_NUMERIC_20_8, nullable=False)
    close: Mapped[Decimal] = mapped_column(_NUMERIC_20_8, nullable=False)
    adjusted_close: Mapped[Decimal] = mapped_column(_NUMERIC_20_8, nullable=False)
    volume: Mapped[int] = mapped_column(nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CorporateActionModel(Base):
    """Per Document 3 §8.1 `corporate_actions` table."""

    __tablename__ = "corporate_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('split','dividend','spinoff')",
            name="ck_corporate_actions_type",
        ),
        UniqueConstraint("instrument_id", "action_type", "ex_date"),
        Index("idx_corporate_actions_instrument_exdate", "instrument_id", "ex_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    ratio: Mapped[Decimal | None] = mapped_column(_NUMERIC_20_8, nullable=True)
    cash_amount: Mapped[Decimal | None] = mapped_column(_NUMERIC_20_8, nullable=True)
    ex_date: Mapped[date] = mapped_column(Date, nullable=False)
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
