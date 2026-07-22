"""Unit tests for the Watchlist aggregate root and WatchlistItem entity."""

from __future__ import annotations

import uuid

import pytest

from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.exceptions import (
    DuplicateWatchlistItemError,
    InvalidWatchlistNameError,
    WatchlistItemNotFoundError,
)
from src.domain.watchlist.value_objects import InstrumentId, WatchlistItemId


def _instrument_id() -> InstrumentId:
    return InstrumentId(uuid.uuid4())


class TestWatchlistCreate:
    def test_creates_with_trimmed_name(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="  My Tech Stocks  ")
        assert watchlist.name == "My Tech Stocks"
        assert watchlist.is_default is False
        assert watchlist.items == []

    def test_can_create_as_default(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Default", is_default=True)
        assert watchlist.is_default is True

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(InvalidWatchlistNameError):
            Watchlist.create(user_id="user-1", name="   ")

    def test_rejects_name_over_max_length(self) -> None:
        with pytest.raises(InvalidWatchlistNameError):
            Watchlist.create(user_id="user-1", name="x" * 101)

    def test_accepts_name_at_max_length(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="x" * 100)
        assert len(watchlist.name) == 100


class TestWatchlistRename:
    def test_renames_and_bumps_updated_at(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Old Name")
        original_updated_at = watchlist.updated_at

        watchlist.rename("New Name")

        assert watchlist.name == "New Name"
        assert watchlist.updated_at >= original_updated_at

    def test_rename_rejects_empty_name(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Old Name")
        with pytest.raises(InvalidWatchlistNameError):
            watchlist.rename("")


class TestWatchlistDefaultFlag:
    def test_mark_as_default(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        watchlist.mark_as_default()
        assert watchlist.is_default is True

    def test_unmark_as_default(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist", is_default=True)
        watchlist.unmark_as_default()
        assert watchlist.is_default is False


class TestWatchlistAddItem:
    def test_adds_item_with_position_zero_when_empty(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        instrument_id = _instrument_id()

        item = watchlist.add_item(instrument_id)

        assert item.instrument_id == instrument_id
        assert item.position == 0
        assert item.is_pinned is False
        assert len(watchlist.items) == 1

    def test_adds_subsequent_items_with_incrementing_position(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        first = watchlist.add_item(_instrument_id())
        second = watchlist.add_item(_instrument_id())

        assert first.position == 0
        assert second.position == 1

    def test_rejects_duplicate_instrument(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        instrument_id = _instrument_id()
        watchlist.add_item(instrument_id)

        with pytest.raises(DuplicateWatchlistItemError):
            watchlist.add_item(instrument_id)

    def test_add_item_bumps_updated_at(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        original_updated_at = watchlist.updated_at
        watchlist.add_item(_instrument_id())
        assert watchlist.updated_at >= original_updated_at


class TestWatchlistRemoveItem:
    def test_removes_item(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        item = watchlist.add_item(_instrument_id())

        watchlist.remove_item(item.id)

        assert watchlist.items == []

    def test_remove_raises_for_unknown_item(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        with pytest.raises(WatchlistItemNotFoundError):
            watchlist.remove_item(WatchlistItemId.new())

    def test_removing_and_readding_same_instrument_is_allowed(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        instrument_id = _instrument_id()
        item = watchlist.add_item(instrument_id)
        watchlist.remove_item(item.id)

        # No DuplicateWatchlistItemError — the instrument is no longer present.
        watchlist.add_item(instrument_id)
        assert len(watchlist.items) == 1


class TestWatchlistPinning:
    def test_pins_an_item(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        item = watchlist.add_item(_instrument_id())

        watchlist.set_pinned(item.id, True)

        assert item.is_pinned is True

    def test_unpins_an_item(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        item = watchlist.add_item(_instrument_id())
        watchlist.set_pinned(item.id, True)

        watchlist.set_pinned(item.id, False)

        assert item.is_pinned is False

    def test_multiple_items_can_be_pinned_simultaneously(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        first = watchlist.add_item(_instrument_id())
        second = watchlist.add_item(_instrument_id())

        watchlist.set_pinned(first.id, True)
        watchlist.set_pinned(second.id, True)

        assert first.is_pinned is True
        assert second.is_pinned is True

    def test_set_pinned_raises_for_unknown_item(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        with pytest.raises(WatchlistItemNotFoundError):
            watchlist.set_pinned(WatchlistItemId.new(), True)


class TestWatchlistReorderItem:
    def test_moves_item_to_the_front(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        first = watchlist.add_item(_instrument_id())
        second = watchlist.add_item(_instrument_id())
        third = watchlist.add_item(_instrument_id())

        watchlist.reorder_item(third.id, 0)

        ordered = sorted(watchlist.items, key=lambda item: item.position)
        assert [item.id for item in ordered] == [third.id, first.id, second.id]

    def test_moves_item_to_the_end(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        first = watchlist.add_item(_instrument_id())
        second = watchlist.add_item(_instrument_id())

        watchlist.reorder_item(first.id, 5)  # beyond range, should clamp to the end

        ordered = sorted(watchlist.items, key=lambda item: item.position)
        assert [item.id for item in ordered] == [second.id, first.id]

    def test_positions_remain_contiguous_after_reorder(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        watchlist.add_item(_instrument_id())
        watchlist.add_item(_instrument_id())
        item = watchlist.add_item(_instrument_id())

        watchlist.reorder_item(item.id, 1)

        positions = sorted(i.position for i in watchlist.items)
        assert positions == [0, 1, 2]

    def test_reorder_raises_for_unknown_item(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        with pytest.raises(WatchlistItemNotFoundError):
            watchlist.reorder_item(WatchlistItemId.new(), 0)
