"""SQLAlchemy declarative models for the Watchlist bounded context.

Per docs/architecture/03-backend-architecture-database-design.md §8.1
(watchlists, watchlist_items) and ADR-0004 (additive columns: is_default +
updated_at on watchlists; position + is_pinned on watchlist_items — no
existing column removed or retyped).

`updated_at` is maintained at the application layer (the mapper writes the
domain entity's computed timestamp onto the model), not via a database
trigger — this matches the exact pattern already established for
PortfolioModel/HoldingModel (see portfolio_mappers.py); no
`set_updated_at()` trigger function exists anywhere in this codebase, so
introducing one here would be a real architectural inconsistency, not a
neutral choice.

These are infrastructure-layer concerns (Document 2 §4.1) — the domain
entities in src.domain.watchlist.entities are the real business objects;
these ORM models exist only to persist them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.postgres.models import Base


class WatchlistModel(Base):
    """Per Document 3 §8.1 `watchlists` table + ADR-0004 (is_default, updated_at)."""

    __tablename__ = "watchlists"
    __table_args__ = (
        Index("idx_watchlists_user", "user_id"),
        Index(
            "idx_watchlists_user_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, server_default="My Watchlist")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    items: Mapped[list[WatchlistItemModel]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan"
    )


class WatchlistItemModel(Base):
    """Per Document 3 §8.1 `watchlist_items` table + ADR-0004 (position, is_pinned)."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "instrument_id"),
        Index("idx_watchlist_items_watchlist_position", "watchlist_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    watchlist: Mapped[WatchlistModel] = relationship(back_populates="items")
