"""watchlist_router.py — HTTP endpoints wiring all watchlist use cases +
the Market Data enrichment integration.

Per ADR-0004's API surface. Every endpoint follows portfolio_router.py's
established pattern: build command/query -> call use case -> map domain
exceptions to HTTP -> return DTO. All watchlist_id path params are scoped
by CurrentUser's user_id (never accepted as a request body/query field for
the owner identity) — Document 3 §7.5's resource-level ownership
enforcement, matching portfolio_router.py exactly.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.application.watchlist.add_remove_watchlist_item_use_case import (
    AddWatchlistItemCommand,
    AddWatchlistItemUseCase,
    RemoveWatchlistItemCommand,
    RemoveWatchlistItemUseCase,
)
from src.application.watchlist.create_watchlist_use_case import (
    CreateWatchlistCommand,
    CreateWatchlistUseCase,
    DeleteWatchlistUseCase,
)
from src.application.watchlist.enrichment_service import (
    EnrichedWatchlist,
    WatchlistEnrichmentService,
)
from src.application.watchlist.ensure_default_watchlist_use_case import (
    EnsureDefaultWatchlistUseCase,
)
from src.application.watchlist.get_watchlist_use_case import (
    GetWatchlistUseCase,
    ListWatchlistsQuery,
    ListWatchlistsUseCase,
)
from src.application.watchlist.update_watchlist_item_use_case import (
    UpdateWatchlistItemCommand,
    UpdateWatchlistItemUseCase,
)
from src.application.watchlist.update_watchlist_use_case import (
    UpdateWatchlistCommand,
    UpdateWatchlistUseCase,
)
from src.domain.market_data.exceptions import MarketDataDomainError
from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.exceptions import WatchlistDomainError
from src.domain.watchlist.value_objects import WatchlistId, WatchlistItemId
from src.presentation.dependencies.auth import CurrentUser, get_current_user
from src.presentation.dependencies.watchlist_use_cases import (
    get_add_watchlist_item_use_case,
    get_create_watchlist_use_case,
    get_delete_watchlist_use_case,
    get_ensure_default_watchlist_use_case,
    get_get_watchlist_use_case,
    get_list_watchlists_use_case,
    get_remove_watchlist_item_use_case,
    get_update_watchlist_item_use_case,
    get_update_watchlist_use_case,
    get_watchlist_enrichment_service,
)
from src.presentation.dto.watchlist_dto import (
    AddWatchlistItemRequest,
    CreateWatchlistRequest,
    UpdateWatchlistItemRequest,
    UpdateWatchlistRequest,
    WatchlistItemQuoteResponse,
    WatchlistItemResponse,
    WatchlistListResponse,
    WatchlistResponse,
    WatchlistSummaryResponse,
)
from src.presentation.market_data_exception_handlers import raise_market_data_exception_as_http
from src.presentation.watchlist_exception_handlers import raise_watchlist_exception_as_http

router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])


def _raise_domain_exception_as_http(exc: Exception) -> None:
    if isinstance(exc, WatchlistDomainError):
        raise_watchlist_exception_as_http(exc)
    elif isinstance(exc, MarketDataDomainError):
        raise_market_data_exception_as_http(exc)
    raise exc


def _watchlist_to_summary_response(watchlist: Watchlist) -> WatchlistSummaryResponse:
    return WatchlistSummaryResponse(
        id=str(watchlist.id),
        user_id=watchlist.user_id,
        name=watchlist.name,
        is_default=watchlist.is_default,
        created_at=watchlist.created_at.isoformat(),
        updated_at=watchlist.updated_at.isoformat(),
        item_count=len(watchlist.items),
    )


def _enriched_watchlist_to_response(enriched: EnrichedWatchlist) -> WatchlistResponse:
    watchlist = enriched.watchlist
    items: list[WatchlistItemResponse] = []
    for item in sorted(watchlist.items, key=lambda i: i.position):
        quote = enriched.quotes_by_item_id.get(str(item.id))
        quote_response = (
            WatchlistItemQuoteResponse(
                price=str(quote.price) if quote.price is not None else None,
                previous_close=(
                    str(quote.previous_close) if quote.previous_close is not None else None
                ),
                daily_change=str(quote.daily_change) if quote.daily_change is not None else None,
                daily_change_pct=(
                    str(quote.daily_change_pct) if quote.daily_change_pct is not None else None
                ),
                source=quote.source,
                is_delayed=quote.is_delayed,
                last_updated=quote.last_updated,
                error=quote.error,
            )
            if quote is not None
            else None
        )
        items.append(
            WatchlistItemResponse(
                id=str(item.id),
                instrument_id=str(item.instrument_id),
                symbol=quote.symbol if quote is not None else None,
                position=item.position,
                is_pinned=item.is_pinned,
                added_at=item.added_at.isoformat(),
                quote=quote_response,
            )
        )

    return WatchlistResponse(
        id=str(watchlist.id),
        user_id=watchlist.user_id,
        name=watchlist.name,
        is_default=watchlist.is_default,
        created_at=watchlist.created_at.isoformat(),
        updated_at=watchlist.updated_at.isoformat(),
        items=items,
        market_status=enriched.market_status,
    )


@router.post("", response_model=WatchlistSummaryResponse, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    body: CreateWatchlistRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[CreateWatchlistUseCase, Depends(get_create_watchlist_use_case)],
) -> WatchlistSummaryResponse:
    watchlist = await use_case.execute(
        CreateWatchlistCommand(
            user_id=str(current_user.user_id), name=body.name, is_default=body.is_default
        )
    )
    return _watchlist_to_summary_response(watchlist)


@router.get("", response_model=WatchlistListResponse)
async def list_watchlists(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    list_use_case: Annotated[ListWatchlistsUseCase, Depends(get_list_watchlists_use_case)],
    ensure_default_use_case: Annotated[
        EnsureDefaultWatchlistUseCase, Depends(get_ensure_default_watchlist_use_case)
    ],
    search: Annotated[str | None, Query()] = None,
    sort_by: Annotated[str, Query()] = "created_at",
    sort_direction: Annotated[str, Query()] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> WatchlistListResponse:
    # Per ADR-0004's design note: a user with zero watchlists gets one
    # lazily provisioned here, on first real dashboard load, rather than
    # eagerly at registration (Auth/Phase 2 is frozen and must not be
    # modified to call this).
    await ensure_default_use_case.execute(str(current_user.user_id))

    result = await list_use_case.execute(
        ListWatchlistsQuery(
            user_id=str(current_user.user_id),
            search=search,
            sort_by=sort_by,  # type: ignore[arg-type]
            sort_direction=sort_direction,  # type: ignore[arg-type]
            page=page,
            page_size=page_size,
        )
    )
    return WatchlistListResponse(
        items=[_watchlist_to_summary_response(w) for w in result.items],
        total_count=result.total_count,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist(
    watchlist_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[GetWatchlistUseCase, Depends(get_get_watchlist_use_case)],
    enrichment_service: Annotated[
        WatchlistEnrichmentService, Depends(get_watchlist_enrichment_service)
    ],
) -> WatchlistResponse:
    try:
        watchlist = await use_case.execute(
            WatchlistId.from_string(watchlist_id), str(current_user.user_id)
        )
    except WatchlistDomainError as exc:
        _raise_domain_exception_as_http(exc)
        raise
    enriched = await enrichment_service.enrich(watchlist)
    return _enriched_watchlist_to_response(enriched)


@router.patch("/{watchlist_id}", response_model=WatchlistSummaryResponse)
async def update_watchlist(
    watchlist_id: str,
    body: UpdateWatchlistRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[UpdateWatchlistUseCase, Depends(get_update_watchlist_use_case)],
) -> WatchlistSummaryResponse:
    try:
        watchlist = await use_case.execute(
            UpdateWatchlistCommand(
                watchlist_id=WatchlistId.from_string(watchlist_id),
                requesting_user_id=str(current_user.user_id),
                name=body.name,
                is_default=body.is_default,
            )
        )
    except WatchlistDomainError as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return _watchlist_to_summary_response(watchlist)


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_watchlist(
    watchlist_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[DeleteWatchlistUseCase, Depends(get_delete_watchlist_use_case)],
) -> None:
    try:
        await use_case.execute(WatchlistId.from_string(watchlist_id), str(current_user.user_id))
    except WatchlistDomainError as exc:
        _raise_domain_exception_as_http(exc)
        raise


@router.post(
    "/{watchlist_id}/items",
    response_model=WatchlistItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_watchlist_item(
    watchlist_id: str,
    body: AddWatchlistItemRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[AddWatchlistItemUseCase, Depends(get_add_watchlist_item_use_case)],
) -> WatchlistItemResponse:
    try:
        item = await use_case.execute(
            AddWatchlistItemCommand(
                watchlist_id=WatchlistId.from_string(watchlist_id),
                requesting_user_id=str(current_user.user_id),
                symbol=body.symbol,
            )
        )
    except (WatchlistDomainError, MarketDataDomainError) as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return WatchlistItemResponse(
        id=str(item.id),
        instrument_id=str(item.instrument_id),
        symbol=body.symbol.upper(),
        position=item.position,
        is_pinned=item.is_pinned,
        added_at=item.added_at.isoformat(),
        quote=None,
    )


@router.patch("/{watchlist_id}/items/{item_id}", response_model=WatchlistItemResponse)
async def update_watchlist_item(
    watchlist_id: str,
    item_id: str,
    body: UpdateWatchlistItemRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[UpdateWatchlistItemUseCase, Depends(get_update_watchlist_item_use_case)],
) -> WatchlistItemResponse:
    try:
        item = await use_case.execute(
            UpdateWatchlistItemCommand(
                watchlist_id=WatchlistId.from_string(watchlist_id),
                requesting_user_id=str(current_user.user_id),
                item_id=WatchlistItemId.from_string(item_id),
                is_pinned=body.is_pinned,
                position=body.position,
            )
        )
    except WatchlistDomainError as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return WatchlistItemResponse(
        id=str(item.id),
        instrument_id=str(item.instrument_id),
        symbol=None,
        position=item.position,
        is_pinned=item.is_pinned,
        added_at=item.added_at.isoformat(),
        quote=None,
    )


@router.delete(
    "/{watchlist_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def remove_watchlist_item(
    watchlist_id: str,
    item_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[RemoveWatchlistItemUseCase, Depends(get_remove_watchlist_item_use_case)],
) -> None:
    try:
        await use_case.execute(
            RemoveWatchlistItemCommand(
                watchlist_id=WatchlistId.from_string(watchlist_id),
                requesting_user_id=str(current_user.user_id),
                item_id=WatchlistItemId.from_string(item_id),
            )
        )
    except WatchlistDomainError as exc:
        _raise_domain_exception_as_http(exc)
        raise
