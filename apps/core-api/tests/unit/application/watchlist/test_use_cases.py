"""Unit tests for the Phase 5 application-layer use cases — CreateWatchlist,
GetWatchlist, ListWatchlists, UpdateWatchlist, DeleteWatchlist,
AddWatchlistItem, RemoveWatchlistItem, UpdateWatchlistItem,
EnsureDefaultWatchlist."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

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
from src.domain.market_data.entities import AssetType, Instrument
from src.domain.market_data.exceptions import InstrumentNotFoundError
from src.domain.market_data.value_objects import InstrumentId as MarketDataInstrumentId
from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.exceptions import (
    DuplicateWatchlistItemError,
    WatchlistNotFoundError,
    WatchlistOwnershipError,
)
from src.domain.watchlist.repositories import WatchlistListFilter, WatchlistPageResult
from src.domain.watchlist.value_objects import InstrumentId, WatchlistId

AAPL_INSTRUMENT_ID = InstrumentId(uuid.uuid4())


class FakeWatchlistRepository:
    def __init__(self) -> None:
        self._store: dict[str, Watchlist] = {}

    async def save(self, watchlist: Watchlist) -> None:
        self._store[str(watchlist.id)] = watchlist

    async def get_by_id(self, watchlist_id: WatchlistId) -> Watchlist | None:
        return self._store.get(str(watchlist_id))

    async def list_for_user(
        self, user_id: str, filters: WatchlistListFilter
    ) -> WatchlistPageResult:
        matching = [w for w in self._store.values() if w.user_id == user_id]
        if filters.search:
            matching = [w for w in matching if filters.search.lower() in w.name.lower()]
        reverse = filters.sort_direction == "desc"
        matching.sort(key=lambda w: getattr(w, filters.sort_by), reverse=reverse)
        return WatchlistPageResult(
            items=tuple(matching), total_count=len(matching), page=1, page_size=20
        )

    async def delete(self, watchlist_id: WatchlistId) -> None:
        self._store.pop(str(watchlist_id), None)

    async def get_default_for_user(self, user_id: str) -> Watchlist | None:
        for watchlist in self._store.values():
            if watchlist.user_id == user_id and watchlist.is_default:
                return watchlist
        return None

    async def count_for_user(self, user_id: str) -> int:
        return sum(1 for w in self._store.values() if w.user_id == user_id)


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


class TestCreateWatchlistUseCase:
    async def test_creates_a_watchlist(self) -> None:
        repo = FakeWatchlistRepository()
        use_case = CreateWatchlistUseCase(repo)

        watchlist = await use_case.execute(
            CreateWatchlistCommand(user_id="user-1", name="Tech Stocks")
        )

        assert watchlist.name == "Tech Stocks"
        assert await repo.get_by_id(watchlist.id) is not None

    async def test_creating_as_default_demotes_previous_default(self) -> None:
        repo = FakeWatchlistRepository()
        use_case = CreateWatchlistUseCase(repo)
        first = await use_case.execute(
            CreateWatchlistCommand(user_id="user-1", name="First", is_default=True)
        )

        second = await use_case.execute(
            CreateWatchlistCommand(user_id="user-1", name="Second", is_default=True)
        )

        refreshed_first = await repo.get_by_id(first.id)
        assert refreshed_first is not None
        assert refreshed_first.is_default is False
        assert second.is_default is True


class TestGetWatchlistUseCase:
    async def test_returns_owned_watchlist(self) -> None:
        repo = FakeWatchlistRepository()
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        await repo.save(watchlist)

        result = await GetWatchlistUseCase(repo).execute(watchlist.id, "user-1")

        assert result.id == watchlist.id

    async def test_raises_not_found_for_unknown_id(self) -> None:
        repo = FakeWatchlistRepository()
        with pytest.raises(WatchlistNotFoundError):
            await GetWatchlistUseCase(repo).execute(WatchlistId.new(), "user-1")

    async def test_raises_ownership_error_for_other_users_watchlist(self) -> None:
        repo = FakeWatchlistRepository()
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        await repo.save(watchlist)

        with pytest.raises(WatchlistOwnershipError):
            await GetWatchlistUseCase(repo).execute(watchlist.id, "user-2")


class TestListWatchlistsUseCase:
    async def test_lists_only_the_requesting_users_watchlists(self) -> None:
        repo = FakeWatchlistRepository()
        await repo.save(Watchlist.create(user_id="user-1", name="Mine"))
        await repo.save(Watchlist.create(user_id="user-2", name="Someone Else's"))

        result = await ListWatchlistsUseCase(repo).execute(ListWatchlistsQuery(user_id="user-1"))

        assert result.total_count == 1
        assert result.items[0].name == "Mine"

    async def test_search_filters_by_name(self) -> None:
        repo = FakeWatchlistRepository()
        await repo.save(Watchlist.create(user_id="user-1", name="Tech Stocks"))
        await repo.save(Watchlist.create(user_id="user-1", name="Energy"))

        result = await ListWatchlistsUseCase(repo).execute(
            ListWatchlistsQuery(user_id="user-1", search="tech")
        )

        assert result.total_count == 1
        assert result.items[0].name == "Tech Stocks"


class TestUpdateWatchlistUseCase:
    async def test_renames(self) -> None:
        repo = FakeWatchlistRepository()
        watchlist = Watchlist.create(user_id="user-1", name="Old Name")
        await repo.save(watchlist)

        updated = await UpdateWatchlistUseCase(repo).execute(
            UpdateWatchlistCommand(
                watchlist_id=watchlist.id, requesting_user_id="user-1", name="New Name"
            )
        )

        assert updated.name == "New Name"

    async def test_setting_default_demotes_previous_default(self) -> None:
        repo = FakeWatchlistRepository()
        first = Watchlist.create(user_id="user-1", name="First", is_default=True)
        second = Watchlist.create(user_id="user-1", name="Second")
        await repo.save(first)
        await repo.save(second)

        await UpdateWatchlistUseCase(repo).execute(
            UpdateWatchlistCommand(
                watchlist_id=second.id, requesting_user_id="user-1", is_default=True
            )
        )

        refreshed_first = await repo.get_by_id(first.id)
        refreshed_second = await repo.get_by_id(second.id)
        assert refreshed_first is not None and refreshed_first.is_default is False
        assert refreshed_second is not None and refreshed_second.is_default is True

    async def test_raises_ownership_error_for_other_users_watchlist(self) -> None:
        repo = FakeWatchlistRepository()
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        await repo.save(watchlist)

        with pytest.raises(WatchlistOwnershipError):
            await UpdateWatchlistUseCase(repo).execute(
                UpdateWatchlistCommand(
                    watchlist_id=watchlist.id, requesting_user_id="user-2", name="Hijacked"
                )
            )


class TestDeleteWatchlistUseCase:
    async def test_deletes_owned_watchlist(self) -> None:
        repo = FakeWatchlistRepository()
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        await repo.save(watchlist)

        await DeleteWatchlistUseCase(repo).execute(watchlist.id, "user-1")

        assert await repo.get_by_id(watchlist.id) is None

    async def test_raises_ownership_error_for_other_users_watchlist(self) -> None:
        repo = FakeWatchlistRepository()
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        await repo.save(watchlist)

        with pytest.raises(WatchlistOwnershipError):
            await DeleteWatchlistUseCase(repo).execute(watchlist.id, "user-2")


class TestAddWatchlistItemUseCase:
    async def test_adds_item_by_symbol(self) -> None:
        watchlist_repo = FakeWatchlistRepository()
        instrument_repo = FakeInstrumentRepository({"AAPL": _aapl_instrument()})
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        await watchlist_repo.save(watchlist)

        item = await AddWatchlistItemUseCase(watchlist_repo, instrument_repo).execute(
            AddWatchlistItemCommand(
                watchlist_id=watchlist.id, requesting_user_id="user-1", symbol="AAPL"
            )
        )

        assert item.instrument_id == AAPL_INSTRUMENT_ID
        refreshed = await watchlist_repo.get_by_id(watchlist.id)
        assert refreshed is not None
        assert len(refreshed.items) == 1

    async def test_raises_for_unknown_symbol(self) -> None:
        watchlist_repo = FakeWatchlistRepository()
        instrument_repo = FakeInstrumentRepository()
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        await watchlist_repo.save(watchlist)

        with pytest.raises(InstrumentNotFoundError):
            await AddWatchlistItemUseCase(watchlist_repo, instrument_repo).execute(
                AddWatchlistItemCommand(
                    watchlist_id=watchlist.id, requesting_user_id="user-1", symbol="ZZZZ"
                )
            )

    async def test_raises_for_duplicate_symbol(self) -> None:
        watchlist_repo = FakeWatchlistRepository()
        instrument_repo = FakeInstrumentRepository({"AAPL": _aapl_instrument()})
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        watchlist.add_item(AAPL_INSTRUMENT_ID)
        await watchlist_repo.save(watchlist)

        with pytest.raises(DuplicateWatchlistItemError):
            await AddWatchlistItemUseCase(watchlist_repo, instrument_repo).execute(
                AddWatchlistItemCommand(
                    watchlist_id=watchlist.id, requesting_user_id="user-1", symbol="AAPL"
                )
            )


class TestRemoveWatchlistItemUseCase:
    async def test_removes_item(self) -> None:
        watchlist_repo = FakeWatchlistRepository()
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        item = watchlist.add_item(AAPL_INSTRUMENT_ID)
        await watchlist_repo.save(watchlist)

        await RemoveWatchlistItemUseCase(watchlist_repo).execute(
            RemoveWatchlistItemCommand(
                watchlist_id=watchlist.id, requesting_user_id="user-1", item_id=item.id
            )
        )

        refreshed = await watchlist_repo.get_by_id(watchlist.id)
        assert refreshed is not None
        assert refreshed.items == []


class TestUpdateWatchlistItemUseCase:
    async def test_pins_an_item(self) -> None:
        watchlist_repo = FakeWatchlistRepository()
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        item = watchlist.add_item(AAPL_INSTRUMENT_ID)
        await watchlist_repo.save(watchlist)

        updated_item = await UpdateWatchlistItemUseCase(watchlist_repo).execute(
            UpdateWatchlistItemCommand(
                watchlist_id=watchlist.id,
                requesting_user_id="user-1",
                item_id=item.id,
                is_pinned=True,
            )
        )

        assert updated_item.is_pinned is True

    async def test_reorders_an_item(self) -> None:
        watchlist_repo = FakeWatchlistRepository()
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        first = watchlist.add_item(AAPL_INSTRUMENT_ID)
        second = watchlist.add_item(InstrumentId(uuid.uuid4()))
        await watchlist_repo.save(watchlist)

        await UpdateWatchlistItemUseCase(watchlist_repo).execute(
            UpdateWatchlistItemCommand(
                watchlist_id=watchlist.id,
                requesting_user_id="user-1",
                item_id=second.id,
                position=0,
            )
        )

        refreshed = await watchlist_repo.get_by_id(watchlist.id)
        assert refreshed is not None
        ordered = sorted(refreshed.items, key=lambda i: i.position)
        assert [i.id for i in ordered] == [second.id, first.id]


class TestEnsureDefaultWatchlistUseCase:
    async def test_creates_default_watchlist_when_user_has_none(self) -> None:
        repo = FakeWatchlistRepository()

        created = await EnsureDefaultWatchlistUseCase(repo).execute("user-1")

        assert created is not None
        assert created.is_default is True
        assert await repo.count_for_user("user-1") == 1

    async def test_does_nothing_when_user_already_has_a_watchlist(self) -> None:
        repo = FakeWatchlistRepository()
        await repo.save(Watchlist.create(user_id="user-1", name="Existing"))

        created = await EnsureDefaultWatchlistUseCase(repo).execute("user-1")

        assert created is None
        assert await repo.count_for_user("user-1") == 1
