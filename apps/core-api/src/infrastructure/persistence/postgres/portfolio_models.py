"""SQLAlchemy declarative models for the Portfolio bounded context.

Per docs/architecture/03-backend-architecture-database-design.md §8.1
(instruments, portfolios, holdings, transactions) and ADR-0003 (split/
transfer_in/transfer_out transaction types + split_ratio/related_portfolio_id
columns).

`InstrumentModel` here is the MINIMAL frozen-architecture `instruments`
table needed as a foreign-key target for holdings/transactions — Document 8
§24's full Market Data Foundation phase (provider ingestion pipeline,
ohlcv_bars, corporate_actions) is NOT part of Phase 3 scope and is not
built here; this table is created now only because Portfolio's schema
depends on it existing, using the exact DDL Document 3 §8.1 already
specifies (no redesign, no forward-guessing of columns beyond what's frozen).

These are infrastructure-layer concerns (Document 2 §4.1) — the domain
entities in src.domain.portfolio.entities are the real business objects;
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.postgres.models import Base

_NUMERIC_20_8 = Numeric(20, 8)


class InstrumentModel(Base):
    """Minimal frozen-architecture `instruments` table (Document 3 §8.1) —
    see module docstring. Populated/extended by the Market Data Foundation
    phase, not Phase 3."""

    __tablename__ = "instruments"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('equity','etf','index','crypto')", name="ck_instruments_asset_type"
        ),
        UniqueConstraint("symbol", "exchange"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="USD")
    ipo_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PortfolioModel(Base):
    """Per Document 3 §8.1 `portfolios` table."""

    __tablename__ = "portfolios"
    __table_args__ = (Index("idx_portfolios_user", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="USD")
    is_paper: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    holdings: Mapped[list[HoldingModel]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    transactions: Mapped[list[TransactionModel]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
        foreign_keys="TransactionModel.portfolio_id",
    )


class HoldingModel(Base):
    """Per Document 3 §8.1 `holdings` table."""

    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("portfolio_id", "instrument_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(_NUMERIC_20_8, nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(_NUMERIC_20_8, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    portfolio: Mapped[PortfolioModel] = relationship(back_populates="holdings")


class TransactionModel(Base):
    """Per Document 3 §8.1 `transactions` table, EXTENDED per ADR-0003:
    `type` CHECK now includes 'split','transfer_in','transfer_out'; adds
    nullable `split_ratio` and `related_portfolio_id` columns (additive
    only — no existing column removed or retyped). Also adds nullable
    `cash_amount` to represent deposit/withdrawal amounts distinctly from
    the per-share `price` column, since those types have no instrument and
    therefore no per-share price."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(
            "type IN ('buy','sell','dividend','split','transfer_in','transfer_out',"
            "'deposit','withdrawal')",
            name="ck_transactions_type",
        ),
        Index("idx_transactions_portfolio_time", "portfolio_id", "executed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(_NUMERIC_20_8, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(_NUMERIC_20_8, nullable=True)
    fees: Mapped[Decimal] = mapped_column(_NUMERIC_20_8, nullable=False, server_default="0")
    split_ratio: Mapped[Decimal | None] = mapped_column(_NUMERIC_20_8, nullable=True)  # ADR-0003
    related_portfolio_id: Mapped[uuid.UUID | None] = mapped_column(  # ADR-0003
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=True
    )
    cash_amount: Mapped[Decimal | None] = mapped_column(_NUMERIC_20_8, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    portfolio: Mapped[PortfolioModel] = relationship(
        back_populates="transactions", foreign_keys=[portfolio_id]
    )
