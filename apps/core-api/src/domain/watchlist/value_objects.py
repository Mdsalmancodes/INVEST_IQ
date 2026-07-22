"""Value objects for the watchlist bounded context.

Per Document 8 §20.2: value objects are plain dataclasses, self-validating
in __post_init__. `InstrumentId` is reused (not duplicated) from
src.domain.portfolio.value_objects — Watchlist references instruments the
same way Portfolio does, and Phase 4 already established this type as
shared across bounded contexts (see market_data's value_objects.py).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from src.domain.portfolio.value_objects import InstrumentId  # noqa: F401 - re-exported

__all__ = ["InstrumentId", "WatchlistId", "WatchlistItemId"]


@dataclass(frozen=True, slots=True)
class WatchlistId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> WatchlistId:
        return cls(uuid.uuid4())

    @classmethod
    def from_string(cls, raw: str) -> WatchlistId:
        return cls(uuid.UUID(raw))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class WatchlistItemId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> WatchlistItemId:
        return cls(uuid.uuid4())

    @classmethod
    def from_string(cls, raw: str) -> WatchlistItemId:
        return cls(uuid.UUID(raw))

    def __str__(self) -> str:
        return str(self.value)
