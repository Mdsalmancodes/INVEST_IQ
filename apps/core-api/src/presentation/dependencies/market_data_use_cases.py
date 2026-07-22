"""Dependency-injection wiring for market_data use cases — mirrors
src.presentation.dependencies.portfolio_use_cases's pattern.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.market_data.get_corporate_actions_use_case import (
    GetCorporateActionsUseCase,
)
from src.application.market_data.get_current_price_use_case import GetCurrentPriceUseCase
from src.application.market_data.get_historical_prices_use_case import (
    GetHistoricalPricesUseCase,
)
from src.application.market_data.get_market_status_use_case import GetMarketStatusUseCase
from src.application.market_data.get_ohlcv_bars_use_case import GetOhlcvBarsUseCase
from src.application.market_data.provider_router import ProviderRouter
from src.application.market_data.search_instruments_use_case import SearchInstrumentsUseCase
from src.application.market_data.validation_service import MarketDataValidationService
from src.infrastructure.market_data.cache import MarketDataCache
from src.infrastructure.market_data.providers.yfinance_provider import YFinanceProvider
from src.infrastructure.persistence.postgres.repositories.corporate_action_repository import (
    SqlAlchemyCorporateActionRepository,
)
from src.infrastructure.persistence.postgres.repositories.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from src.infrastructure.persistence.postgres.repositories.ohlcv_bar_repository import (
    SqlAlchemyOhlcvBarRepository,
)
from src.infrastructure.persistence.postgres.session import get_db_session
from src.infrastructure.persistence.redis.clients import RedisClients, get_redis_clients


def get_provider_router() -> ProviderRouter:
    # Per Document 5 §11.1: yfinance is dev-only, "never used in
    # production." A production deployment would configure this with a
    # paid provider (Polygon/Alpha Vantage with a real key) first,
    # yfinance last or excluded entirely — this phase's DI wiring uses
    # yfinance as the sole provider since no paid credentials exist in
    # this environment (disclosed limitation, consistent with the
    # AlphaVantageProvider/Celery task's own disclosed scope).
    yfinance_provider = YFinanceProvider()
    return ProviderRouter(
        quote_providers=(yfinance_provider,),
        historical_providers=(yfinance_provider,),
    )


def get_validation_service() -> MarketDataValidationService:
    return MarketDataValidationService()


def get_market_data_cache(
    redis_clients: Annotated[RedisClients, Depends(get_redis_clients)],
) -> MarketDataCache:
    return MarketDataCache(redis_clients.cache)


def get_get_current_price_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    provider_router: Annotated[ProviderRouter, Depends(get_provider_router)],
    cache: Annotated[MarketDataCache, Depends(get_market_data_cache)],
) -> GetCurrentPriceUseCase:
    return GetCurrentPriceUseCase(
        SqlAlchemyInstrumentRepository(session),
        SqlAlchemyOhlcvBarRepository(session),
        provider_router,
        cache,
    )


def get_get_ohlcv_bars_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    provider_router: Annotated[ProviderRouter, Depends(get_provider_router)],
    validation_service: Annotated[MarketDataValidationService, Depends(get_validation_service)],
) -> GetOhlcvBarsUseCase:
    return GetOhlcvBarsUseCase(
        SqlAlchemyInstrumentRepository(session),
        SqlAlchemyOhlcvBarRepository(session),
        provider_router,
        validation_service,
    )


def get_get_historical_prices_use_case(
    ohlcv_use_case: Annotated[GetOhlcvBarsUseCase, Depends(get_get_ohlcv_bars_use_case)],
) -> GetHistoricalPricesUseCase:
    return GetHistoricalPricesUseCase(ohlcv_use_case)


def get_get_corporate_actions_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GetCorporateActionsUseCase:
    return GetCorporateActionsUseCase(
        SqlAlchemyInstrumentRepository(session), SqlAlchemyCorporateActionRepository(session)
    )


def get_get_market_status_use_case() -> GetMarketStatusUseCase:
    return GetMarketStatusUseCase()


def get_search_instruments_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SearchInstrumentsUseCase:
    return SearchInstrumentsUseCase(SqlAlchemyInstrumentRepository(session))
