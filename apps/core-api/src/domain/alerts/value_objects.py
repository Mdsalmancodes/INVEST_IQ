"""Value objects for the alerts bounded context.

Per Document 8 §20.2: value objects are plain dataclasses, self-validating
in __post_init__. `InstrumentId` is reused (not duplicated) from
src.domain.portfolio.value_objects — Alerts reference instruments the
same way Watchlist and Portfolio do (see watchlist/value_objects.py for
the same convention applied there).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from src.domain.portfolio.value_objects import InstrumentId  # noqa: F401 - re-exported

__all__ = ["AlertId", "InstrumentId"]


@dataclass(frozen=True, slots=True)
class AlertId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> AlertId:
        return cls(uuid.uuid4())

    @classmethod
    def from_string(cls, raw: str) -> AlertId:
        return cls(uuid.UUID(raw))

    def __str__(self) -> str:
        return str(self.value)
