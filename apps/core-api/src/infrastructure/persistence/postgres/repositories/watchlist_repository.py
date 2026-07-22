"""SqlAlchemyWatchlistRepository — implements
src.domain.watchlist.repositories.WatchlistRepository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.repositories import WatchlistListFilter, WatchlistPageResult
from src.domain.watchlist.value_objects import WatchlistId
from src.infrastructure.persistence.postgres.repositories.watchlist_mappers import (
    watchlist_item_to_model,
    watchlist_to_domain,
    watchlist_to_model,
)
from src.infrastructure.persistence.postgres.watchlist_models import (
    WatchlistModel,
)

_SORT_COLUMNS = {
    "name": WatchlistModel.name,
    "created_at": WatchlistModel.created_at,
    "updated_at": WatchlistModel.updated_at,
}


class SqlAlchemyWatchlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, watchlist: Watchlist) -> None:
        existing = await self._session.get(
            WatchlistModel, watchlist.id.value, options=[selectinload(WatchlistModel.items)]
        )
        model = watchlist_to_model(watchlist, existing=existing)
        if existing is None:
            self._session.add(model)

        existing_item_models_by_id = (
            {item.id: item for item in existing.items} if existing is not None else {}
        )
        current_item_ids = {item.id.value for item in watchlist.items}

        # Delete orphaned items — the aggregate's in-memory `items` list is
        # the single source of truth (Watchlist.remove_item() removes from
        # it), so any persisted item no longer present must be deleted.
        # This is the one genuine difference from PortfolioRepository.save()
        # (which never needs to delete a Holding via this path); Watchlist
        # items are explicitly, routinely removed as a first-class operation.
        for existing_id, existing_item_model in existing_item_models_by_id.items():
            if existing_id not in current_item_ids:
                await self._session.delete(existing_item_model)

        for item in watchlist.items:
            matching_existing_model = existing_item_models_by_id.get(item.id.value)
            item_model = watchlist_item_to_model(
                item, watchlist.id, existing=matching_existing_model
            )
            if matching_existing_model is None:
                self._session.add(item_model)

        await self._session.flush()

    async def get_by_id(self, watchlist_id: WatchlistId) -> Watchlist | None:
        stmt = (
            select(WatchlistModel)
            .where(WatchlistModel.id == watchlist_id.value)
            .options(selectinload(WatchlistModel.items))
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return watchlist_to_domain(model) if model is not None else None

    async def list_for_user(
        self, user_id: str, filters: WatchlistListFilter
    ) -> WatchlistPageResult:
        base_stmt = select(WatchlistModel).where(WatchlistModel.user_id == user_id)
        if filters.search:
            base_stmt = base_stmt.where(WatchlistModel.name.ilike(f"%{filters.search}%"))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_count = (await self._session.execute(count_stmt)).scalar_one()

        sort_column = _SORT_COLUMNS[filters.sort_by]
        ordered_column = (
            sort_column.desc() if filters.sort_direction == "desc" else sort_column.asc()
        )

        page_stmt = (
            base_stmt.options(selectinload(WatchlistModel.items))
            .order_by(ordered_column)
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        result = await self._session.execute(page_stmt)
        models = result.scalars().all()
        items = tuple(watchlist_to_domain(model) for model in models)
        return WatchlistPageResult(
            items=items, total_count=total_count, page=filters.page, page_size=filters.page_size
        )

    async def delete(self, watchlist_id: WatchlistId) -> None:
        model = await self._session.get(WatchlistModel, watchlist_id.value)
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()

    async def get_default_for_user(self, user_id: str) -> Watchlist | None:
        stmt = (
            select(WatchlistModel)
            .where(WatchlistModel.user_id == user_id, WatchlistModel.is_default.is_(True))
            .options(selectinload(WatchlistModel.items))
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return watchlist_to_domain(model) if model is not None else None

    async def count_for_user(self, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(WatchlistModel)
            .where(WatchlistModel.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
