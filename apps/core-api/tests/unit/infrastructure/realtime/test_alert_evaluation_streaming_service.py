"""Tests for AlertEvaluationStreamingService — real Alert/Notification
entities via the real EvaluateAlertsUseCase (task 8's own engine),
fakes at the repository boundary, matching every other Phase 9 streaming
service's established test convention."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

from src.domain.alerts.entities import Alert
from src.domain.alerts.repositories import AlertListFilter, AlertPageResult
from src.domain.alerts.value_objects import AlertId, InstrumentId
from src.domain.market_data.entities import AssetType, Instrument, OhlcvBar
from src.domain.market_data.repositories import OhlcvBarQuery
from src.domain.market_data.value_objects import InstrumentId as MarketDataInstrumentId
from src.domain.notifications.entities import Notification
from src.domain.notifications.value_objects import NotificationId
from src.infrastructure.realtime import channels
from src.infrastructure.realtime.alert_evaluation_streaming_service import (
    AlertEvaluationDependencies,
    AlertEvaluationStreamingService,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
AAPL_ID = InstrumentId(uuid.uuid4())


class FakeRedisBroker:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, object]]] = []

    async def publish(self, channel: str, payload: dict[str, object]) -> None:
        self.published.append((channel, payload))


class FakeAlertRepository:
    def __init__(self, alerts: list[Alert]) -> None:
        self._store: dict[str, Alert] = {str(a.id): a for a in alerts}

    async def save(self, alert: Alert) -> None:
        self._store[str(alert.id)] = alert

    async def get_by_id(self, alert_id: AlertId) -> Alert | None:
        return self._store.get(str(alert_id))

    async def list_for_user(self, user_id: str, filters: AlertListFilter) -> AlertPageResult:
        raise NotImplementedError

    async def list_active_for_instrument(self, instrument_id: InstrumentId) -> tuple[Alert, ...]:
        return tuple(
            a for a in self._store.values() if a.instrument_id == instrument_id and a.is_active
        )

    async def delete(self, alert_id: AlertId) -> None:
        self._store.pop(str(alert_id), None)

    async def exists_duplicate(self, *args: object, **kwargs: object) -> bool:
        return False


class FakeNotificationRepository:
    def __init__(self) -> None:
        self.saved: list[Notification] = []

    async def save(self, notification: Notification) -> None:
        self.saved.append(notification)

    async def get_by_id(self, notification_id: NotificationId) -> Notification | None:
        return None

    async def list_for_user(self, user_id: str, filters: object) -> object:
        raise NotImplementedError

    async def mark_all_as_read_for_user(self, user_id: str) -> int:
        raise NotImplementedError


class FakeInstrumentRepository:
    async def get_by_symbol(self, symbol: str) -> Instrument | None:
        if symbol != "AAPL":
            return None
        return Instrument(
            id=MarketDataInstrumentId(AAPL_ID.value),
            symbol="AAPL",
            exchange="NASDAQ",
            name="Apple Inc.",
            asset_type=AssetType.EQUITY,
            currency="USD",
            sector=None,
            industry=None,
            ipo_date=None,
            is_active=True,
            created_at=NOW,
        )


class FakeOhlcvBarRepository:
    async def query(self, query: OhlcvBarQuery) -> tuple[OhlcvBar, ...]:
        return ()


def _make_alert(condition_type: str, threshold: str) -> Alert:
    return Alert.create(
        user_id=str(uuid.uuid4()),
        instrument_id=AAPL_ID,
        condition_type=condition_type,  # type: ignore[arg-type]
        threshold=Decimal(threshold),
    )


def _build_service(
    redis_broker: FakeRedisBroker, alerts: list[Alert]
) -> AlertEvaluationStreamingService:
    alert_repo = FakeAlertRepository(alerts)
    notification_repo = FakeNotificationRepository()

    @asynccontextmanager
    async def session_scope() -> AsyncIterator[object]:
        yield object()

    def dependency_factory(_session: object) -> AlertEvaluationDependencies:
        return AlertEvaluationDependencies(
            alert_repository=alert_repo,  # type: ignore[arg-type]
            notification_repository=notification_repo,  # type: ignore[arg-type]
            instrument_repository=FakeInstrumentRepository(),  # type: ignore[arg-type]
            ohlcv_bar_repository=FakeOhlcvBarRepository(),  # type: ignore[arg-type]
        )

    return AlertEvaluationStreamingService(
        redis_broker=redis_broker,  # type: ignore[arg-type]
        session_scope=session_scope,
        dependency_factory=dependency_factory,
    )


class TestHandleQuote:
    async def test_publishes_a_notification_to_the_triggering_users_alert_channel(self) -> None:
        alert = _make_alert("price_above", "100")
        broker = FakeRedisBroker()
        service = _build_service(broker, [alert])

        notifications = await service.handle_quote("AAPL", {"price": "101"})

        assert len(notifications) == 1
        expected_channel = channels.alert_channel(alert.user_id)
        matching = [(c, p) for c, p in broker.published if c == expected_channel]
        assert len(matching) == 1
        _, payload = matching[0]
        assert payload["type"] == "alert_triggered"

    async def test_does_not_publish_when_no_alert_condition_is_met(self) -> None:
        alert = _make_alert("price_above", "500")
        broker = FakeRedisBroker()
        service = _build_service(broker, [alert])

        notifications = await service.handle_quote("AAPL", {"price": "101"})

        assert notifications == ()
        assert broker.published == []

    async def test_does_nothing_for_an_unknown_symbol(self) -> None:
        alert = _make_alert("price_above", "100")
        broker = FakeRedisBroker()
        service = _build_service(broker, [alert])

        notifications = await service.handle_quote("UNKNOWN", {"price": "101"})

        assert notifications == ()
        assert broker.published == []

    async def test_a_quote_payload_with_no_price_field_is_a_no_op(self) -> None:
        alert = _make_alert("price_above", "100")
        broker = FakeRedisBroker()
        service = _build_service(broker, [alert])

        notifications = await service.handle_quote("AAPL", {})

        assert notifications == ()
        assert broker.published == []
