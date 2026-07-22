"""Domain entities for the watchlist bounded context.

Per Document 3 §8.1 (watchlists/watchlist_items) and ADR-0004 (is_default,
updated_at, position, is_pinned). The Watchlist aggregate root owns its
WatchlistItems — no code outside this module mutates a WatchlistItem's
position/pinned state directly; all mutations go through Watchlist's
methods to guarantee the no-duplicate-symbol and ordering invariants,
mirroring Portfolio's "aggregate owns its children" rule (Document 3 §3.4
rule #1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.domain.watchlist.exceptions import (
    DuplicateWatchlistItemError,
    InvalidWatchlistNameError,
    WatchlistItemNotFoundError,
)
from src.domain.watchlist.value_objects import InstrumentId, WatchlistId, WatchlistItemId

MAX_NAME_LENGTH = 100


@dataclass(slots=True)
class WatchlistItem:
    """A single tracked instrument within a Watchlist.

    `position` is user-controlled display order (ADR-0004), distinct from
    `added_at` (insertion order) — reordering rewrites `position` without
    touching `added_at`, so "recently added" and "my custom order" remain
    independently queryable.
    """

    id: WatchlistItemId
    instrument_id: InstrumentId
    position: int
    is_pinned: bool
    added_at: datetime

    @classmethod
    def create(cls, instrument_id: InstrumentId, position: int) -> WatchlistItem:
        return cls(
            id=WatchlistItemId.new(),
            instrument_id=instrument_id,
            position=position,
            is_pinned=False,
            added_at=datetime.now(UTC),
        )


@dataclass(slots=True)
class Watchlist:
    """Aggregate root. Per ADR-0004: `is_default` is enforced at-most-one-
    per-user at the database layer (partial unique index); this class only
    enforces the invariants that are genuinely aggregate-local (no
    duplicate symbol, valid name, positions stay consistent) — it does NOT
    itself check "is there already a default watchlist for this user"
    since that requires cross-aggregate knowledge the Watchlist entity
    correctly has no access to (that check belongs to the application-layer
    use case, which can query the repository).
    """

    id: WatchlistId
    user_id: str
    name: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    items: list[WatchlistItem] = field(default_factory=list)

    @classmethod
    def create(cls, user_id: str, name: str, is_default: bool = False) -> Watchlist:
        validated_name = _validate_name(name)
        now = datetime.now(UTC)
        return cls(
            id=WatchlistId.new(),
            user_id=user_id,
            name=validated_name,
            is_default=is_default,
            created_at=now,
            updated_at=now,
            items=[],
        )

    def rename(self, new_name: str) -> None:
        self.name = _validate_name(new_name)
        self.updated_at = datetime.now(UTC)

    def mark_as_default(self) -> None:
        self.is_default = True
        self.updated_at = datetime.now(UTC)

    def unmark_as_default(self) -> None:
        self.is_default = False
        self.updated_at = datetime.now(UTC)

    def add_item(self, instrument_id: InstrumentId) -> WatchlistItem:
        """Raises DuplicateWatchlistItemError if instrument_id is already
        present — the domain-level companion to the DB's
        UNIQUE(watchlist_id, instrument_id) constraint, so the rule is
        enforced before a repository round-trip (Document 3 §3.4's
        aggregate-invariant pattern, applied here)."""
        if any(item.instrument_id == instrument_id for item in self.items):
            raise DuplicateWatchlistItemError(
                f"Instrument {instrument_id} is already in this watchlist"
            )
        next_position = max((item.position for item in self.items), default=-1) + 1
        new_item = WatchlistItem.create(instrument_id, next_position)
        self.items.append(new_item)
        self.updated_at = datetime.now(UTC)
        return new_item

    def remove_item(self, item_id: WatchlistItemId) -> None:
        item = self._find_item(item_id)
        self.items.remove(item)
        self.updated_at = datetime.now(UTC)

    def set_pinned(self, item_id: WatchlistItemId, is_pinned: bool) -> None:
        item = self._find_item(item_id)
        item.is_pinned = is_pinned
        self.updated_at = datetime.now(UTC)

    def reorder_item(self, item_id: WatchlistItemId, new_position: int) -> None:
        """Moves `item_id` to `new_position`, shifting every other item's
        position accordingly (a full-rewrite reorder — ADR-0004's disclosed
        alternative to fractional indexing, justified by watchlists being
        small collections)."""
        target = self._find_item(item_id)
        others = [item for item in self.items if item.id != item_id]
        others.sort(key=lambda item: item.position)

        clamped_position = max(0, min(new_position, len(others)))
        others.insert(clamped_position, target)
        for index, item in enumerate(others):
            item.position = index
        self.updated_at = datetime.now(UTC)

    def _find_item(self, item_id: WatchlistItemId) -> WatchlistItem:
        for item in self.items:
            if item.id == item_id:
                return item
        raise WatchlistItemNotFoundError(f"Watchlist item {item_id} not found")


def _validate_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise InvalidWatchlistNameError("Watchlist name cannot be empty")
    if len(stripped) > MAX_NAME_LENGTH:
        raise InvalidWatchlistNameError(
            f"Watchlist name cannot exceed {MAX_NAME_LENGTH} characters, got {len(stripped)}"
        )
    return stripped
