"""Dependency-injection wiring for portfolio use cases — mirrors
src.presentation.dependencies.use_cases's pattern for auth.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.auth.audit_logger import AuditLogger
from src.application.portfolio.add_transaction_use_case import AddTransactionUseCase
from src.application.portfolio.calculation_service import PortfolioCalculationService
from src.application.portfolio.create_portfolio_use_case import CreatePortfolioUseCase
from src.application.portfolio.get_holdings_use_case import GetHoldingsUseCase
from src.application.portfolio.get_portfolio_summary_use_case import GetPortfolioSummaryUseCase
from src.application.portfolio.get_portfolio_use_case import (
    GetPortfolioUseCase,
    ListPortfoliosUseCase,
)
from src.application.portfolio.list_transactions_use_case import ListTransactionsUseCase
from src.application.portfolio.price_provider import PriceProvider
from src.application.portfolio.update_portfolio_use_case import (
    DeletePortfolioUseCase,
    UpdatePortfolioUseCase,
)
from src.config import Settings, get_settings
from src.infrastructure.market_data.real_price_provider import RealPriceProvider
from src.infrastructure.persistence.postgres.repositories.audit_log_repository import (
    SqlAlchemyAuditLogRepository,
)
from src.infrastructure.persistence.postgres.repositories.ohlcv_bar_repository import (
    SqlAlchemyOhlcvBarRepository,
)
from src.infrastructure.persistence.postgres.repositories.portfolio_repository import (
    SqlAlchemyPortfolioRepository,
)
from src.infrastructure.persistence.postgres.repositories.transaction_repository import (
    SqlAlchemyTransactionRepository,
)
from src.infrastructure.persistence.postgres.session import get_db_session


def get_create_portfolio_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CreatePortfolioUseCase:
    return CreatePortfolioUseCase(SqlAlchemyPortfolioRepository(session))


def get_get_portfolio_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GetPortfolioUseCase:
    return GetPortfolioUseCase(SqlAlchemyPortfolioRepository(session))


def get_list_portfolios_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ListPortfoliosUseCase:
    return ListPortfoliosUseCase(SqlAlchemyPortfolioRepository(session))


def get_update_portfolio_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UpdatePortfolioUseCase:
    return UpdatePortfolioUseCase(SqlAlchemyPortfolioRepository(session))


def get_delete_portfolio_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DeletePortfolioUseCase:
    return DeletePortfolioUseCase(SqlAlchemyPortfolioRepository(session))


def get_add_transaction_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AddTransactionUseCase:
    return AddTransactionUseCase(
        SqlAlchemyPortfolioRepository(session),
        SqlAlchemyTransactionRepository(session),
        audit_logger=AuditLogger(SqlAlchemyAuditLogRepository(session)),
        large_transaction_threshold_usd=settings.large_transaction_audit_threshold_usd,
    )


def get_list_transactions_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ListTransactionsUseCase:
    return ListTransactionsUseCase(
        SqlAlchemyPortfolioRepository(session), SqlAlchemyTransactionRepository(session)
    )


def get_get_holdings_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GetHoldingsUseCase:
    return GetHoldingsUseCase(SqlAlchemyPortfolioRepository(session))


def get_price_provider(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PriceProvider:
    return RealPriceProvider(SqlAlchemyOhlcvBarRepository(session))


def get_calculation_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    price_provider: Annotated[PriceProvider, Depends(get_price_provider)],
) -> PortfolioCalculationService:
    return PortfolioCalculationService(price_provider, SqlAlchemyTransactionRepository(session))


def get_get_portfolio_summary_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    calculation_service: Annotated[PortfolioCalculationService, Depends(get_calculation_service)],
) -> GetPortfolioSummaryUseCase:
    return GetPortfolioSummaryUseCase(SqlAlchemyPortfolioRepository(session), calculation_service)
