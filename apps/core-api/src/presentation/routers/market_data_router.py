"""market_data_router.py — HTTP endpoints wiring all 5 market data use
cases (Current Price, Historical Price, OHLCV, Corporate Actions, Market
Status).

SECURITY NOTE (disclosed decision, not a silent gap): these endpoints are
UNAUTHENTICATED — no bearer token required, unlike portfolio_router.py's
endpoints. This mirrors how real trading platforms treat stock quotes/
historical prices/corporate actions as public reference data (the same
data anyone can see on a public stock-quote website), and the frozen
Document 4 catalog lists /instruments/* endpoints with no auth annotation,
unlike /portfolios/* which is inherently user-owned private data. If the
founder wants these gated behind auth (e.g. to enforce a paid-tier rate
limit per Document 5 §11.1's FeatureEntitlement concept), that requires
its own ADR — not silently added here.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.market_data.get_corporate_actions_use_case import (
    GetCorporateActionsUseCase,
)
from src.application.market_data.get_current_price_use_case import GetCurrentPriceUseCase
from src.application.market_data.get_historical_prices_use_case import (
    GetHistoricalPricesUseCase,
)
from src.application.market_data.get_market_status_use_case import GetMarketStatusUseCase
from src.application.market_data.get_ohlcv_bars_use_case import GetOhlcvBarsUseCase
from src.application.market_data.search_instruments_use_case import SearchInstrumentsUseCase
from src.domain.market_data.exceptions import InvalidIntervalError, MarketDataDomainError
from src.domain.market_data.value_objects import Interval
from src.presentation.dependencies.market_data_use_cases import (
    get_get_corporate_actions_use_case,
    get_get_current_price_use_case,
    get_get_historical_prices_use_case,
    get_get_market_status_use_case,
    get_get_ohlcv_bars_use_case,
    get_search_instruments_use_case,
)
from src.presentation.dto.market_data_dto import (
    CorporateActionListResponse,
    CorporateActionResponse,
    CurrentPriceResponse,
    HistoricalPricesResponse,
    InstrumentSearchResponse,
    InstrumentSearchResultResponse,
    MarketStatusResponse,
    OhlcvBarResponse,
    OhlcvBarsResponse,
    PricePointResponse,
)
from src.presentation.market_data_exception_handlers import raise_market_data_exception_as_http

router = APIRouter(prefix="/api/v1", tags=["market-data"])


def _parse_interval(raw: str) -> Interval:
    try:
        return Interval.from_string(raw)
    except InvalidIntervalError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


def _parse_date_range(start: str | None, end: str | None) -> tuple[date, date]:
    try:
        parsed_end = date.fromisoformat(end) if end is not None else date.today()
        parsed_start = date.fromisoformat(start) if start is not None else parsed_end.replace(day=1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid date format (expected YYYY-MM-DD): {exc}",
        ) from exc
    return parsed_start, parsed_end


@router.get("/instruments/search", response_model=InstrumentSearchResponse)
async def search_instruments(
    use_case: Annotated[SearchInstrumentsUseCase, Depends(get_search_instruments_use_case)],
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> InstrumentSearchResponse:
    results = await use_case.execute(q, limit)
    return InstrumentSearchResponse(
        items=[
            InstrumentSearchResultResponse(
                id=str(instrument.id),
                symbol=instrument.symbol,
                exchange=instrument.exchange,
                name=instrument.name,
                asset_type=instrument.asset_type.value,
                currency=instrument.currency,
            )
            for instrument in results
        ]
    )


@router.get("/instruments/{symbol}/quote", response_model=CurrentPriceResponse)
async def get_current_price(
    symbol: str,
    use_case: Annotated[GetCurrentPriceUseCase, Depends(get_get_current_price_use_case)],
) -> CurrentPriceResponse:
    try:
        result = await use_case.execute(symbol)
    except MarketDataDomainError as exc:
        raise_market_data_exception_as_http(exc)
        raise
    return CurrentPriceResponse(
        symbol=result.symbol,
        price=str(result.price.amount),
        previous_close=str(result.previous_close.amount) if result.previous_close else None,
        source=result.source,
        is_stale_fallback=result.is_stale_fallback,
    )


@router.get("/instruments/{symbol}/prices", response_model=HistoricalPricesResponse)
async def get_historical_prices(
    symbol: str,
    use_case: Annotated[GetHistoricalPricesUseCase, Depends(get_get_historical_prices_use_case)],
    interval: Annotated[str, Query()] = "1d",
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
) -> HistoricalPricesResponse:
    parsed_interval = _parse_interval(interval)
    parsed_start, parsed_end = _parse_date_range(start, end)
    try:
        result = await use_case.execute(symbol, parsed_interval, parsed_start, parsed_end)
    except MarketDataDomainError as exc:
        raise_market_data_exception_as_http(exc)
        raise
    return HistoricalPricesResponse(
        symbol=result.symbol,
        interval=result.interval.value,
        points=[
            PricePointResponse(as_of=p.as_of.isoformat(), price=str(p.price.amount))
            for p in result.points
        ],
        data_completeness=result.data_completeness,
    )


@router.get("/instruments/{symbol}/bars", response_model=OhlcvBarsResponse)
async def get_ohlcv_bars(
    symbol: str,
    use_case: Annotated[GetOhlcvBarsUseCase, Depends(get_get_ohlcv_bars_use_case)],
    interval: Annotated[str, Query()] = "1d",
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
) -> OhlcvBarsResponse:
    parsed_interval = _parse_interval(interval)
    parsed_start, parsed_end = _parse_date_range(start, end)
    try:
        result = await use_case.execute(symbol, parsed_interval, parsed_start, parsed_end)
    except MarketDataDomainError as exc:
        raise_market_data_exception_as_http(exc)
        raise
    return OhlcvBarsResponse(
        symbol=result.symbol,
        interval=result.interval.value,
        bars=[
            OhlcvBarResponse(
                bar_time=bar.bar_time.isoformat(),
                open=str(bar.open.amount),
                high=str(bar.high.amount),
                low=str(bar.low.amount),
                close=str(bar.close.amount),
                adjusted_close=str(bar.adjusted_close.amount),
                volume=bar.volume,
                is_closed=bar.is_closed,
                source=bar.source,
            )
            for bar in result.bars
        ],
        data_completeness=result.data_completeness,
    )


@router.get("/instruments/{symbol}/corporate-actions", response_model=CorporateActionListResponse)
async def get_corporate_actions(
    symbol: str,
    use_case: Annotated[GetCorporateActionsUseCase, Depends(get_get_corporate_actions_use_case)],
) -> CorporateActionListResponse:
    try:
        actions = await use_case.execute(symbol)
    except MarketDataDomainError as exc:
        raise_market_data_exception_as_http(exc)
        raise
    return CorporateActionListResponse(
        items=[
            CorporateActionResponse(
                id=str(action.id),
                action_type=action.action_type.value,
                ratio=str(action.ratio) if action.ratio is not None else None,
                cash_amount=(
                    str(action.cash_amount.amount) if action.cash_amount is not None else None
                ),
                ex_date=action.ex_date.isoformat(),
                announced_at=action.announced_at.isoformat() if action.announced_at else None,
            )
            for action in actions
        ]
    )


@router.get("/market/status", response_model=MarketStatusResponse)
async def get_market_status(
    use_case: Annotated[GetMarketStatusUseCase, Depends(get_get_market_status_use_case)],
) -> MarketStatusResponse:
    result = use_case.execute()
    return MarketStatusResponse(
        is_open=result.is_open,
        session=result.session,
        as_of=result.as_of.isoformat(),
        next_open=result.next_open.isoformat() if result.next_open else None,
    )
