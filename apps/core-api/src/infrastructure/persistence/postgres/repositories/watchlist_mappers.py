"""Domain <-> ORM mapping functions for the watchlist bounded context.

Mirrors the pattern in portfolio_mappers.py — pure functions, no side
effects, isolate the domain layer from SQLAlchemy model shape.
"""

from __future__ import annotations

from src.domain.watchlist.entities import Watchlist, WatchlistItem
from src.domain.watchlist.value_objects import InstrumentId, WatchlistId, WatchlistItemId
from src.infrastructure.persistence.postgres.watchlist_models import (
    WatchlistItemModel,
    WatchlistModel,
)


def watchlist_item_to_domain(model: WatchlistItemModel) -> WatchlistItem:
    return WatchlistItem(
        id=WatchlistItemId(model.id),
        instrument_id=InstrumentId(model.instrument_id),
        position=model.position,
        is_pinned=model.is_pinned,
        added_at=model.added_at,
    )


def watchlist_item_to_model(
    item: WatchlistItem, watchlist_id: WatchlistId, existing: WatchlistItemModel | None
) -> WatchlistItemModel:
    model = existing if existing is not None else WatchlistItemModel(id=item.id.value)
    model.watchlist_id = watchlist_id.value
    model.instrument_id = item.instrument_id.value
    model.position = item.position
    model.is_pinned = item.is_pinned
    model.added_at = item.added_at
    return model


def watchlist_to_domain(model: WatchlistModel) -> Watchlist:
    watchlist = Watchlist(
        id=WatchlistId(model.id),
        user_id=str(model.user_id),
        name=model.name,
        is_default=model.is_default,
        created_at=model.created_at,
        updated_at=model.updated_at,
        items=[],
    )
    watchlist.items = [watchlist_item_to_domain(item_model) for item_model in model.items]
    return watchlist


def watchlist_to_model(watchlist: Watchlist, existing: WatchlistModel | None) -> WatchlistModel:
    model = existing if existing is not None else WatchlistModel(id=watchlist.id.value)
    model.user_id = watchlist.user_id  # type: ignore[assignment]  # str -> UUID column, driver-coerced
    model.name = watchlist.name
    model.is_default = watchlist.is_default
    model.created_at = watchlist.created_at
    model.updated_at = watchlist.updated_at
    return model
