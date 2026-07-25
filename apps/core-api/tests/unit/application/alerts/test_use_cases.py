"""Unit tests for the Phase 6 application-layer use cases — CreateAlert,
GetAlert, ListAlerts, UpdateAlert, DeleteAlert."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.application.alerts.create_alert_use_case import (
    CreateAlertCommand,
    CreateAlertUseCase,
    DeleteAlertUseCase,
)
from src.application.alerts.get_alert_use_case import (
    GetAlertUseCase,
    ListAlertsQuery,
    ListAlertsUseCase,
)
from src.application.alerts.update_alert_use_case import UpdateAlertCommand, UpdateAlertUseCase
from src.domain.alerts.entities import Alert
from src.domain.alerts.exceptions import (
    AlertNotFoundError,
    AlertOwnershipError,
    DuplicateAlertError,
)
from src.domain.alerts.repositories import AlertListFilter, AlertPageResult
from src.domain.alerts.value_objects import AlertId, InstrumentId
from src.domain.market_data.entities import AssetType, Instrument
from src.domain.market_data.exceptions import InstrumentNotFoundError
from src.domain.market_data.value_objects import InstrumentId as MarketDataInstrumentId

AAPL_INSTRUMENT_ID = InstrumentId(uuid.uuid4())


class FakeAlertRepository:
    def __init__(self) -> None:
        self._store: dict[str, Alert] = {}

    async def save(self, alert: Alert) -> None:
        self._store[str(alert.id)] = alert

    async def get_by_id(self, alert_id: AlertId) -> Alert | None:
        return self._store.get(str(alert_id))

    async def list_for_user(self, user_id: str, filters: AlertListFilter) -> AlertPageResult:
        matching = [a for a in self._store.values() if a.user_id == user_id]
        if filters.is_active is not None:
            matching = [a for a in matching if a.is_active == filters.is_active]
        reverse = filters.sort_direction == "desc"
        matching.sort(key=lambda a: getattr(a, filters.sort_by), reverse=reverse)
        return AlertPageResult(
            items=tuple(matching), total_count=len(matching), page=1, page_size=20
        )

    async def list_active_for_instrument(self, instrument_id: InstrumentId) -> tuple[Alert, ...]:
        return tuple(
            a
            for a in self._store.values()
            if a.instrument_id == instrument_id and a.is_active
        )

    async def delete(self, alert_id: AlertId) -> None:
        self._store.pop(str(alert_id), None)

    async def exists_duplicate(
        self,
        user_id: str,
        instrument_id: InstrumentId,
        condition_type: str,
        threshold: object,
        exclude_alert_id: AlertId | None = None,
    ) -> bool:
        return any(
            a.user_id == user_id
            and a.instrument_id == instrument_id
            and a.condition_type == condition_type
            and a.threshold == threshold
            and (exclude_alert_id is None or a.id != exclude_alert_id)
            for a in self._store.values()
        )


class FakeInstrumentRepository:
    def __init__(self, instruments: dict[str, Instrument] | None = None) -> None:
        self._by_symbol = instruments or {}

    async def save(self, instrument: Instrument) -> None:
        self._by_symbol[instrument.symbol] = instrument

    async def get_by_id(self, instrument_id: object) -> Instrument | None:
        raise NotImplementedError

    async def get_by_symbol(self, symbol: str) -> Instrument | None:
        return self._by_symbol.get(symbol)

    async def search(self, query: str, limit: int = 20) -> tuple[Instrument, ...]:
        raise NotImplementedError


def _aapl_instrument() -> Instrument:
    return Instrument(
        id=MarketDataInstrumentId(AAPL_INSTRUMENT_ID.value),
        symbol="AAPL",
        exchange="NASDAQ",
        name="Apple Inc.",
        asset_type=AssetType.EQUITY,
        currency="USD",
        sector=None,
        industry=None,
        ipo_date=None,
        is_active=True,
        created_at=datetime.now(UTC),
    )


class TestCreateAlertUseCase:
    async def test_creates_an_alert_by_symbol(self) -> None:
        alert_repo = FakeAlertRepository()
        instrument_repo = FakeInstrumentRepository({"AAPL": _aapl_instrument()})

        alert = await CreateAlertUseCase(alert_repo, instrument_repo).execute(
            CreateAlertCommand(
                user_id="user-1",
                symbol="AAPL",
                condition_type="price_above",
                threshold=Decimal("150"),
            )
        )

        assert alert.instrument_id == AAPL_INSTRUMENT_ID
        assert await alert_repo.get_by_id(alert.id) is not None

    async def test_raises_for_unknown_symbol(self) -> None:
        alert_repo = FakeAlertRepository()
        instrument_repo = FakeInstrumentRepository()

        with pytest.raises(InstrumentNotFoundError):
            await CreateAlertUseCase(alert_repo, instrument_repo).execute(
                CreateAlertCommand(
                    user_id="user-1",
                    symbol="ZZZZ",
                    condition_type="price_above",
                    threshold=Decimal("150"),
                )
            )

    async def test_raises_for_duplicate_alert(self) -> None:
        alert_repo = FakeAlertRepository()
        instrument_repo = FakeInstrumentRepository({"AAPL": _aapl_instrument()})
        command = CreateAlertCommand(
            user_id="user-1",
            symbol="AAPL",
            condition_type="price_above",
            threshold=Decimal("150"),
        )
        await CreateAlertUseCase(alert_repo, instrument_repo).execute(command)

        with pytest.raises(DuplicateAlertError):
            await CreateAlertUseCase(alert_repo, instrument_repo).execute(command)

    async def test_allows_different_condition_types_for_same_instrument(self) -> None:
        alert_repo = FakeAlertRepository()
        instrument_repo = FakeInstrumentRepository({"AAPL": _aapl_instrument()})
        await CreateAlertUseCase(alert_repo, instrument_repo).execute(
            CreateAlertCommand(
                user_id="user-1",
                symbol="AAPL",
                condition_type="price_above",
                threshold=Decimal("150"),
            )
        )

        alert = await CreateAlertUseCase(alert_repo, instrument_repo).execute(
            CreateAlertCommand(
                user_id="user-1",
                symbol="AAPL",
                condition_type="price_below",
                threshold=Decimal("150"),
            )
        )

        assert alert.condition_type == "price_below"


class TestGetAlertUseCase:
    async def test_returns_owned_alert(self) -> None:
        repo = FakeAlertRepository()
        alert = Alert.create(
            user_id="user-1",
            instrument_id=AAPL_INSTRUMENT_ID,
            condition_type="price_above",
            threshold=Decimal("150"),
        )
        await repo.save(alert)

        result = await GetAlertUseCase(repo).execute(alert.id, "user-1")

        assert result.id == alert.id

    async def test_raises_not_found_for_unknown_id(self) -> None:
        repo = FakeAlertRepository()
        with pytest.raises(AlertNotFoundError):
            await GetAlertUseCase(repo).execute(AlertId.new(), "user-1")

    async def test_raises_ownership_error_for_other_users_alert(self) -> None:
        repo = FakeAlertRepository()
        alert = Alert.create(
            user_id="user-1",
            instrument_id=AAPL_INSTRUMENT_ID,
            condition_type="price_above",
            threshold=Decimal("150"),
        )
        await repo.save(alert)

        with pytest.raises(AlertOwnershipError):
            await GetAlertUseCase(repo).execute(alert.id, "user-2")


class TestListAlertsUseCase:
    async def test_lists_only_the_requesting_users_alerts(self) -> None:
        repo = FakeAlertRepository()
        await repo.save(
            Alert.create(
                user_id="user-1",
                instrument_id=AAPL_INSTRUMENT_ID,
                condition_type="price_above",
                threshold=Decimal("150"),
            )
        )
        await repo.save(
            Alert.create(
                user_id="user-2",
                instrument_id=InstrumentId(uuid.uuid4()),
                condition_type="price_above",
                threshold=Decimal("50"),
            )
        )

        result = await ListAlertsUseCase(repo).execute(ListAlertsQuery(user_id="user-1"))

        assert result.total_count == 1
        assert result.items[0].user_id == "user-1"

    async def test_filters_by_is_active(self) -> None:
        repo = FakeAlertRepository()
        active = Alert.create(
            user_id="user-1",
            instrument_id=AAPL_INSTRUMENT_ID,
            condition_type="price_above",
            threshold=Decimal("150"),
        )
        inactive = Alert.create(
            user_id="user-1",
            instrument_id=InstrumentId(uuid.uuid4()),
            condition_type="price_below",
            threshold=Decimal("50"),
        )
        inactive.deactivate()
        await repo.save(active)
        await repo.save(inactive)

        result = await ListAlertsUseCase(repo).execute(
            ListAlertsQuery(user_id="user-1", is_active=True)
        )

        assert result.total_count == 1
        assert result.items[0].id == active.id


class TestUpdateAlertUseCase:
    async def test_updates_threshold(self) -> None:
        repo = FakeAlertRepository()
        alert = Alert.create(
            user_id="user-1",
            instrument_id=AAPL_INSTRUMENT_ID,
            condition_type="price_above",
            threshold=Decimal("150"),
        )
        await repo.save(alert)

        updated = await UpdateAlertUseCase(repo).execute(
            UpdateAlertCommand(
                alert_id=alert.id, requesting_user_id="user-1", threshold=Decimal("175")
            )
        )

        assert updated.threshold == Decimal("175")

    async def test_deactivates_alert(self) -> None:
        repo = FakeAlertRepository()
        alert = Alert.create(
            user_id="user-1",
            instrument_id=AAPL_INSTRUMENT_ID,
            condition_type="price_above",
            threshold=Decimal("150"),
        )
        await repo.save(alert)

        updated = await UpdateAlertUseCase(repo).execute(
            UpdateAlertCommand(alert_id=alert.id, requesting_user_id="user-1", is_active=False)
        )

        assert updated.is_active is False

    async def test_raises_ownership_error_for_other_users_alert(self) -> None:
        repo = FakeAlertRepository()
        alert = Alert.create(
            user_id="user-1",
            instrument_id=AAPL_INSTRUMENT_ID,
            condition_type="price_above",
            threshold=Decimal("150"),
        )
        await repo.save(alert)

        with pytest.raises(AlertOwnershipError):
            await UpdateAlertUseCase(repo).execute(
                UpdateAlertCommand(
                    alert_id=alert.id, requesting_user_id="user-2", threshold=Decimal("999")
                )
            )


class TestDeleteAlertUseCase:
    async def test_deletes_owned_alert(self) -> None:
        repo = FakeAlertRepository()
        alert = Alert.create(
            user_id="user-1",
            instrument_id=AAPL_INSTRUMENT_ID,
            condition_type="price_above",
            threshold=Decimal("150"),
        )
        await repo.save(alert)

        await DeleteAlertUseCase(repo).execute(alert.id, "user-1")

        assert await repo.get_by_id(alert.id) is None

    async def test_raises_ownership_error_for_other_users_alert(self) -> None:
        repo = FakeAlertRepository()
        alert = Alert.create(
            user_id="user-1",
            instrument_id=AAPL_INSTRUMENT_ID,
            condition_type="price_above",
            threshold=Decimal("150"),
        )
        await repo.save(alert)

        with pytest.raises(AlertOwnershipError):
            await DeleteAlertUseCase(repo).execute(alert.id, "user-2")
