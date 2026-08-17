from src.infrastructure.persistence.postgres.session import get_session_factory

from src.infrastructure.persistence.postgres.repositories.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from src.infrastructure.persistence.postgres.repositories.ohlcv_bar_repository import (
    SqlAlchemyOhlcvBarRepository,
)

from src.application.market_data.provider_router import ProviderRouter
from src.application.market_data.validation_service import MarketDataValidationService

from src.infrastructure.market_data.providers.yfinance_provider import YFinanceProvider


def build_dependencies():
    session_factory = get_session_factory()

    # ✅ CREATE REAL SESSION HERE
    session = session_factory()

    # ✅ PASS REAL SESSION (NOT FACTORY, NOT FUNCTION)
    instrument_repo = SqlAlchemyInstrumentRepository(session)
    ohlcv_repo = SqlAlchemyOhlcvBarRepository(session)

    provider_router = ProviderRouter(
        quote_providers=(YFinanceProvider(),),
        historical_providers=(YFinanceProvider(),),
    )

    validation_service = MarketDataValidationService()

    return (
        instrument_repo,
        ohlcv_repo,
        provider_router,
        validation_service,
    )