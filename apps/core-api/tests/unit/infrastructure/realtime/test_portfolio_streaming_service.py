"""Tests for PortfolioStreamingService — real ConnectionManager, real
Portfolio/Transaction entities, real PortfolioCalculationService (all
pure, no I/O), fakes only for the repository boundary, matching
test_watchlist_streaming_service.py's own established convention."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

from src.application.portfolio.calculation_service import PortfolioCalculationService
from src.domain.market_data.entities import AssetType, Instrument
from src.domain.market_data.value_objects import InstrumentId as MarketDataInstrumentId
from src.domain.portfolio.entities import Portfolio, Transaction, TransactionType
from src.domain.portfolio.repositories import (
    PageResult,
    PortfolioListFilter,
    PortfolioPageResult,
    TransactionFilter,
)
from src.domain.portfolio.value_objects import (
    InstrumentId,
    Money,
    PortfolioId,
    Quantity,
    TransactionId,
)
from src.infrastructure.realtime import channels
from src.infrastructure.realtime.connection_manager import ConnectionManager
from src.infrastructure.realtime.portfolio_streaming_service import (
    PortfolioStreamingDependencies,
    PortfolioStreamingService,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
TECH_INSTRUMENT = InstrumentId(uuid.uuid4())


class FakeWebSocket:
    async def accept(self) -> None:
        pass

    async def send_json(self, message: dict[str, object]) -> None:
        pass


class FakeRedisBroker:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, object]]] = []

    async def publish(self, channel: str, payload: dict[str, object]) -> None:
        self.published.append((channel, payload))


class FakePriceProvider:
    async def get_current_price(self, instrument_id: InstrumentId) -> Money | None:
        return Money(Decimal("100"))

    async def get_previous_close(self, instrument_id: InstrumentId) -> Money | None:
        return None


class FakeTransactionRepository:
    async def save(self, transaction: Transaction) -> None:
        pass

    async def get_by_id(self, transaction_id: TransactionId) -> Transaction | None:
        return None

    async def list_for_portfolio(
        self, portfolio_id: PortfolioId, filters: TransactionFilter
    ) -> PageResult:
        return PageResult(items=(), total_count=0, page=1, page_size=20)

    async def list_all_for_portfolio_unpaginated(
        self, portfolio_id: PortfolioId
    ) -> tuple[Transaction, ...]:
        return ()


class FakeInstrumentRepository:
    async def get_by_id(self, instrument_id: InstrumentId) -> Instrument | None:
        return Instrument(
            id=MarketDataInstrumentId(instrument_id.value),
            symbol="TECH",
            exchange="NASDAQ",
            name="Tech Inc.",
            asset_type=AssetType.EQUITY,
            currency="USD",
            sector="Technology",
            industry=None,
            ipo_date=None,
            is_active=True,
            created_at=NOW,
        )


class FakePortfolioRepository:
    def __init__(self, portfolios_by_user: dict[str, list[Portfolio]]) -> None:
        self._by_user = portfolios_by_user

    async def list_for_user(
        self, user_id: str, filters: PortfolioListFilter
    ) -> PortfolioPageResult:
        items = tuple(self._by_user.get(user_id, []))
        return PortfolioPageResult(
            items=items, total_count=len(items), page=filters.page, page_size=filters.page_size
        )


def _make_portfolio(user_id: str) -> Portfolio:
    portfolio = Portfolio(
        id=PortfolioId.new(),
        user_id=user_id,
        name="My Portfolio",
        base_currency="USD",
        is_paper=False,
        created_at=NOW,
        updated_at=NOW,
    )
    portfolio.apply_transaction(
        Transaction(
            id=TransactionId.new(),
            portfolio_id=portfolio.id,
            instrument_id=TECH_INSTRUMENT,
            type=TransactionType.BUY,
            quantity=Quantity(Decimal("10")),
            price=Money(Decimal("100")),
            fees=Money(Decimal("0")),
            split_ratio=None,
            related_portfolio_id=None,
            cash_amount=None,
            executed_at=NOW,
            created_at=NOW,
        )
    )
    return portfolio


def _build_service(
    connection_manager: ConnectionManager,
    redis_broker: FakeRedisBroker,
    portfolios_by_user: dict[str, list[Portfolio]],
) -> PortfolioStreamingService:
    portfolio_repo = FakePortfolioRepository(portfolios_by_user)

    @asynccontextmanager
    async def session_scope() -> AsyncIterator[object]:
        yield object()

    def dependency_factory(_session: object) -> PortfolioStreamingDependencies:
        return PortfolioStreamingDependencies(
            portfolio_repository=portfolio_repo,  # type: ignore[arg-type]
            instrument_repository=FakeInstrumentRepository(),  # type: ignore[arg-type]
            calculation_service=PortfolioCalculationService(
                FakePriceProvider(), FakeTransactionRepository()  # type: ignore[arg-type]
            ),
        )

    return PortfolioStreamingService(
        connection_manager=connection_manager,
        redis_broker=redis_broker,  # type: ignore[arg-type]
        session_scope=session_scope,
        dependency_factory=dependency_factory,
        poll_interval_seconds=10.0,
    )


class TestTick:
    async def test_publishes_nothing_when_no_client_is_subscribed_to_a_portfolio_topic(
        self,
    ) -> None:
        manager = ConnectionManager()
        broker = FakeRedisBroker()
        service = _build_service(manager, broker, {"user-1": [_make_portfolio("user-1")]})

        await service.tick()

        assert broker.published == []

    async def test_publishes_a_portfolio_summary_for_a_subscribed_user(self) -> None:
        manager = ConnectionManager()
        portfolio = _make_portfolio("user-1")
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe([f"portfolio:{portfolio.id}"])
        broker = FakeRedisBroker()
        service = _build_service(manager, broker, {"user-1": [portfolio]})

        await service.tick()

        expected_channel = channels.portfolio_channel("user-1", str(portfolio.id))
        matching = [(c, p) for c, p in broker.published if c == expected_channel]
        assert len(matching) == 1
        _, payload = matching[0]
        assert payload["portfolio_id"] == str(portfolio.id)
        assert Decimal(str(payload["current_value"])) == Decimal("1000")
        assert Decimal(str(payload["total_investment"])) == Decimal("1000")
        sector_allocation = payload["sector_allocation"]
        assert len(sector_allocation) == 1  # type: ignore[arg-type]
        assert sector_allocation[0]["sector"] == "Technology"  # type: ignore[index]

    async def test_does_not_publish_for_a_user_not_subscribed_to_any_portfolio(self) -> None:
        manager = ConnectionManager()
        portfolio_one = _make_portfolio("user-1")
        portfolio_two = _make_portfolio("user-2")
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe([f"portfolio:{portfolio_one.id}"])
        await manager.connect("user-2", FakeWebSocket())  # type: ignore[arg-type]
        broker = FakeRedisBroker()
        service = _build_service(
            manager, broker, {"user-1": [portfolio_one], "user-2": [portfolio_two]}
        )

        await service.tick()

        published_channels = {c for c, _ in broker.published}
        assert channels.portfolio_channel("user-1", str(portfolio_one.id)) in published_channels
        assert channels.portfolio_channel("user-2", str(portfolio_two.id)) not in published_channels
