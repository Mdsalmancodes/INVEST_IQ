"""Dependency-injection wiring for watchlist use cases — mirrors
src.presentation.dependencies.portfolio_use_cases's pattern.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.market_data.get_current_price_use_case import GetCurrentPriceUseCase
from src.application.market_data.get_market_status_use_case import GetMarketStatusUseCase
from src.application.watchlist.add_remove_watchlist_item_use_case import (
    AddWatchlistItemUseCase,
    RemoveWatchlistItemUseCase,
)
from src.application.watchlist.create_watchlist_use_case import (
    CreateWatchlistUseCase,
    DeleteWatchlistUseCase,
)
from src.application.watchlist.enrichment_service import WatchlistEnrichmentService
from src.application.watchlist.ensure_default_watchlist_use_case import (
    EnsureDefaultWatchlistUseCase,
)
from src.application.watchlist.get_watchlist_use_case import (
    GetWatchlistUseCase,
    ListWatchlistsUseCase,
)
from src.application.watchlist.update_watchlist_item_use_case import UpdateWatchlistItemUseCase
from src.application.watchlist.update_watchlist_use_case import UpdateWatchlistUseCase
from src.infrastructure.persistence.postgres.repositories.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from src.infrastructure.persistence.postgres.repositories.watchlist_repository import (
    SqlAlchemyWatchlistRepository,
)
from src.infrastructure.persistence.postgres.session import get_db_session
from src.presentation.dependencies.market_data_use_cases import (
    get_get_current_price_use_case,
    get_get_market_status_use_case,
)


def get_create_watchlist_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CreateWatchlistUseCase:
    return CreateWatchlistUseCase(SqlAlchemyWatchlistRepository(session))


def get_get_watchlist_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GetWatchlistUseCase:
    return GetWatchlistUseCase(SqlAlchemyWatchlistRepository(session))


def get_list_watchlists_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ListWatchlistsUseCase:
    return ListWatchlistsUseCase(SqlAlchemyWatchlistRepository(session))


def get_update_watchlist_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UpdateWatchlistUseCase:
    return UpdateWatchlistUseCase(SqlAlchemyWatchlistRepository(session))


def get_delete_watchlist_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DeleteWatchlistUseCase:
    return DeleteWatchlistUseCase(SqlAlchemyWatchlistRepository(session))


def get_add_watchlist_item_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AddWatchlistItemUseCase:
    return AddWatchlistItemUseCase(
        SqlAlchemyWatchlistRepository(session), SqlAlchemyInstrumentRepository(session)
    )


def get_remove_watchlist_item_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RemoveWatchlistItemUseCase:
    return RemoveWatchlistItemUseCase(SqlAlchemyWatchlistRepository(session))


def get_update_watchlist_item_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UpdateWatchlistItemUseCase:
    return UpdateWatchlistItemUseCase(SqlAlchemyWatchlistRepository(session))


def get_ensure_default_watchlist_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EnsureDefaultWatchlistUseCase:
    return EnsureDefaultWatchlistUseCase(SqlAlchemyWatchlistRepository(session))


def get_watchlist_enrichment_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_price_use_case: Annotated[
        GetCurrentPriceUseCase, Depends(get_get_current_price_use_case)
    ],
    market_status_use_case: Annotated[
        GetMarketStatusUseCase, Depends(get_get_market_status_use_case)
    ],
) -> WatchlistEnrichmentService:
    return WatchlistEnrichmentService(
        SqlAlchemyInstrumentRepository(session), current_price_use_case, market_status_use_case
    )
