"""portfolio_router.py — HTTP endpoints wiring all 9 portfolio use cases.

Per Document 3 §3.4/§7.5 and ADR-0003. Every endpoint follows the auth
router's established pattern: build command/query -> call use case -> map
domain exceptions to HTTP via raise_portfolio_exception_as_http() -> return
DTO. All portfolio_id path params are scoped by CurrentUser's user_id
(never accepted as a request body/query field for the owner identity) —
Document 3 §7.5's resource-level ownership enforcement.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.portfolio.add_transaction_use_case import (
    AddTransactionCommand,
)
from src.application.portfolio.add_transaction_use_case import (
    AddTransactionUseCase as AddTransactionUseCaseType,
)
from src.application.portfolio.create_portfolio_use_case import CreatePortfolioCommand
from src.application.portfolio.create_portfolio_use_case import (
    CreatePortfolioUseCase as CreatePortfolioUseCaseType,
)
from src.application.portfolio.get_holdings_use_case import (
    GetHoldingsUseCase as GetHoldingsUseCaseType,
)
from src.application.portfolio.get_portfolio_summary_use_case import (
    GetPortfolioSummaryUseCase as GetPortfolioSummaryUseCaseType,
)
from src.application.portfolio.get_portfolio_use_case import (
    GetPortfolioUseCase as GetPortfolioUseCaseType,
)
from src.application.portfolio.get_portfolio_use_case import ListPortfoliosQuery
from src.application.portfolio.get_portfolio_use_case import (
    ListPortfoliosUseCase as ListPortfoliosUseCaseType,
)
from src.application.portfolio.list_transactions_use_case import ListTransactionsQuery
from src.application.portfolio.list_transactions_use_case import (
    ListTransactionsUseCase as ListTransactionsUseCaseType,
)
from src.application.portfolio.update_portfolio_use_case import (
    DeletePortfolioUseCase,
    UpdatePortfolioCommand,
)
from src.application.portfolio.update_portfolio_use_case import (
    UpdatePortfolioUseCase as UpdatePortfolioUseCaseType,
)
from src.domain.portfolio.entities import Portfolio, TransactionType
from src.domain.portfolio.exceptions import InvalidTransactionError, PortfolioDomainError
from src.domain.portfolio.value_objects import InstrumentId, Money, PortfolioId, Quantity
from src.presentation.dependencies.auth import CurrentUser, get_current_user
from src.presentation.dependencies.portfolio_use_cases import (
    get_add_transaction_use_case,
    get_create_portfolio_use_case,
    get_delete_portfolio_use_case,
    get_get_holdings_use_case,
    get_get_portfolio_summary_use_case,
    get_get_portfolio_use_case,
    get_list_portfolios_use_case,
    get_list_transactions_use_case,
    get_update_portfolio_use_case,
)
from src.presentation.dto.portfolio_dto import (
    AddTransactionRequest,
    CreatePortfolioRequest,
    HoldingListResponse,
    HoldingResponse,
    HoldingSummaryResponse,
    PortfolioListResponse,
    PortfolioResponse,
    PortfolioSummaryResponse,
    TransactionListResponse,
    TransactionResponse,
    UpdatePortfolioRequest,
)
from src.presentation.portfolio_exception_handlers import raise_portfolio_exception_as_http

router = APIRouter(prefix="/api/v1/portfolios", tags=["portfolios"])


def _portfolio_to_response(portfolio: Portfolio) -> PortfolioResponse:
    return PortfolioResponse(
        id=str(portfolio.id),
        user_id=portfolio.user_id,
        name=portfolio.name,
        base_currency=portfolio.base_currency,
        is_paper=portfolio.is_paper,
        created_at=portfolio.created_at.isoformat(),
        updated_at=portfolio.updated_at.isoformat(),
    )


def _parse_decimal_field(raw: str | None, field_name: str) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid decimal value for {field_name!r}: {raw!r}",
        ) from exc


@router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    body: CreatePortfolioRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[CreatePortfolioUseCaseType, Depends(get_create_portfolio_use_case)],
) -> PortfolioResponse:
    portfolio = await use_case.execute(
        CreatePortfolioCommand(
            user_id=str(current_user.user_id),
            name=body.name,
            base_currency=body.base_currency,
            is_paper=body.is_paper,
        )
    )
    return _portfolio_to_response(portfolio)


@router.get("", response_model=PortfolioListResponse)
async def list_portfolios(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[ListPortfoliosUseCaseType, Depends(get_list_portfolios_use_case)],
    is_paper: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PortfolioListResponse:
    result = await use_case.execute(
        ListPortfoliosQuery(
            user_id=str(current_user.user_id),
            is_paper=is_paper,
            page=page,
            page_size=page_size,
        )
    )
    return PortfolioListResponse(
        items=[_portfolio_to_response(p) for p in result.items],
        total_count=result.total_count,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(
    portfolio_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[GetPortfolioUseCaseType, Depends(get_get_portfolio_use_case)],
) -> PortfolioResponse:
    try:
        portfolio = await use_case.execute(
            PortfolioId.from_string(portfolio_id), str(current_user.user_id)
        )
    except PortfolioDomainError as exc:
        raise_portfolio_exception_as_http(exc)
        raise
    return _portfolio_to_response(portfolio)


@router.patch("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: str,
    body: UpdatePortfolioRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[UpdatePortfolioUseCaseType, Depends(get_update_portfolio_use_case)],
) -> PortfolioResponse:
    try:
        portfolio = await use_case.execute(
            UpdatePortfolioCommand(
                portfolio_id=PortfolioId.from_string(portfolio_id),
                requesting_user_id=str(current_user.user_id),
                name=body.name,
                base_currency=body.base_currency,
            )
        )
    except PortfolioDomainError as exc:
        raise_portfolio_exception_as_http(exc)
        raise
    return _portfolio_to_response(portfolio)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_portfolio(
    portfolio_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[DeletePortfolioUseCase, Depends(get_delete_portfolio_use_case)],
) -> None:
    try:
        await use_case.execute(PortfolioId.from_string(portfolio_id), str(current_user.user_id))
    except PortfolioDomainError as exc:
        raise_portfolio_exception_as_http(exc)
        raise


@router.post(
    "/{portfolio_id}/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_transaction(
    portfolio_id: str,
    body: AddTransactionRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[AddTransactionUseCaseType, Depends(get_add_transaction_use_case)],
) -> TransactionResponse:
    try:
        transaction_type = TransactionType(body.type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid transaction type: {body.type!r}",
        ) from exc

    quantity = _parse_decimal_field(body.quantity, "quantity")
    price = _parse_decimal_field(body.price, "price")
    fees = _parse_decimal_field(body.fees, "fees") or Decimal("0")
    cash_amount = _parse_decimal_field(body.cash_amount, "cash_amount")

    try:
        result = await use_case.execute(
            AddTransactionCommand(
                portfolio_id=PortfolioId.from_string(portfolio_id),
                requesting_user_id=str(current_user.user_id),
                type=transaction_type,
                executed_at=datetime.fromisoformat(body.executed_at),
                instrument_id=(
                    InstrumentId.from_string(body.instrument_id)
                    if body.instrument_id is not None
                    else None
                ),
                quantity=Quantity(quantity) if quantity is not None else None,
                price=Money(price) if price is not None else None,
                fees=Money(fees),
                split_ratio=body.split_ratio,
                related_portfolio_id=(
                    PortfolioId.from_string(body.related_portfolio_id)
                    if body.related_portfolio_id is not None
                    else None
                ),
                cash_amount=Money(cash_amount) if cash_amount is not None else None,
            )
        )
    except (PortfolioDomainError, InvalidTransactionError) as exc:
        raise_portfolio_exception_as_http(exc)
        raise

    tx = result.transaction
    return TransactionResponse(
        id=str(tx.id),
        portfolio_id=str(tx.portfolio_id),
        instrument_id=str(tx.instrument_id) if tx.instrument_id else None,
        type=tx.type.value,
        quantity=str(tx.quantity.value) if tx.quantity else None,
        price=str(tx.price.amount) if tx.price else None,
        fees=str(tx.fees.amount),
        split_ratio=tx.split_ratio,
        related_portfolio_id=str(tx.related_portfolio_id) if tx.related_portfolio_id else None,
        cash_amount=str(tx.cash_amount.amount) if tx.cash_amount else None,
        executed_at=tx.executed_at.isoformat(),
        created_at=tx.created_at.isoformat(),
        realized_gain=(str(result.realized_gain.gain.amount) if result.realized_gain else None),
    )


@router.get("/{portfolio_id}/transactions", response_model=TransactionListResponse)
async def list_transactions(
    portfolio_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[ListTransactionsUseCaseType, Depends(get_list_transactions_use_case)],
    instrument_id: Annotated[str | None, Query()] = None,
    type_: Annotated[list[str] | None, Query(alias="type")] = None,
    executed_after: Annotated[str | None, Query()] = None,
    executed_before: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TransactionListResponse:
    try:
        result = await use_case.execute(
            ListTransactionsQuery(
                portfolio_id=PortfolioId.from_string(portfolio_id),
                requesting_user_id=str(current_user.user_id),
                instrument_id=(
                    InstrumentId.from_string(instrument_id) if instrument_id is not None else None
                ),
                types=(tuple(TransactionType(t) for t in type_) if type_ is not None else None),
                executed_after=(
                    datetime.fromisoformat(executed_after) if executed_after is not None else None
                ),
                executed_before=(
                    datetime.fromisoformat(executed_before) if executed_before is not None else None
                ),
                page=page,
                page_size=page_size,
            )
        )
    except PortfolioDomainError as exc:
        raise_portfolio_exception_as_http(exc)
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return TransactionListResponse(
        items=[
            TransactionResponse(
                id=str(tx.id),
                portfolio_id=str(tx.portfolio_id),
                instrument_id=str(tx.instrument_id) if tx.instrument_id else None,
                type=tx.type.value,
                quantity=str(tx.quantity.value) if tx.quantity else None,
                price=str(tx.price.amount) if tx.price else None,
                fees=str(tx.fees.amount),
                split_ratio=tx.split_ratio,
                related_portfolio_id=(
                    str(tx.related_portfolio_id) if tx.related_portfolio_id else None
                ),
                cash_amount=str(tx.cash_amount.amount) if tx.cash_amount else None,
                executed_at=tx.executed_at.isoformat(),
                created_at=tx.created_at.isoformat(),
            )
            for tx in result.items
        ],
        total_count=result.total_count,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{portfolio_id}/holdings", response_model=HoldingListResponse)
async def get_holdings(
    portfolio_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[GetHoldingsUseCaseType, Depends(get_get_holdings_use_case)],
) -> HoldingListResponse:
    try:
        holdings = await use_case.execute(
            PortfolioId.from_string(portfolio_id), str(current_user.user_id)
        )
    except PortfolioDomainError as exc:
        raise_portfolio_exception_as_http(exc)
        raise
    return HoldingListResponse(
        items=[
            HoldingResponse(
                id=str(h.id),
                instrument_id=str(h.instrument_id),
                quantity=str(h.quantity.value),
                average_cost=str(h.average_cost.amount),
            )
            for h in holdings
        ]
    )


@router.get("/{portfolio_id}/summary", response_model=PortfolioSummaryResponse)
async def get_portfolio_summary(
    portfolio_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    use_case: Annotated[
        GetPortfolioSummaryUseCaseType, Depends(get_get_portfolio_summary_use_case)
    ],
) -> PortfolioSummaryResponse:
    try:
        summary = await use_case.execute(
            PortfolioId.from_string(portfolio_id), str(current_user.user_id)
        )
    except PortfolioDomainError as exc:
        raise_portfolio_exception_as_http(exc)
        raise
    return PortfolioSummaryResponse(
        portfolio_id=summary.portfolio_id,
        total_investment=str(summary.total_investment.amount),
        current_value=str(summary.current_value.amount),
        profit_loss=str(summary.profit_loss.amount),
        profit_loss_pct=str(summary.profit_loss_pct),
        realized_gain=str(summary.realized_gain.amount),
        unrealized_gain=str(summary.unrealized_gain.amount),
        dividend_income=str(summary.dividend_income.amount),
        daily_gain=str(summary.daily_gain.amount),
        holdings=[
            HoldingSummaryResponse(
                instrument_id=str(h.instrument_id),
                quantity=str(h.quantity),
                average_buy_price=str(h.average_buy_price.amount),
                current_price=str(h.current_price.amount) if h.current_price else None,
                market_value=str(h.market_value.amount) if h.market_value else None,
                unrealized_gain=str(h.unrealized_gain.amount) if h.unrealized_gain else None,
                allocation_pct=str(h.allocation_pct) if h.allocation_pct is not None else None,
                daily_gain=str(h.daily_gain.amount) if h.daily_gain else None,
            )
            for h in summary.holdings
        ],
        holdings_missing_price=list(summary.holdings_missing_price),
    )
