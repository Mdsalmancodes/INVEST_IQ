"""Value objects for the notifications bounded context.

Per Document 8 §20.2: value objects are plain dataclasses, self-validating
in __post_init__ — matching alerts/value_objects.py's convention for this
same pair of contexts (Document 5 §12.2's notifications table).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

__all__ = ["NotificationId"]


@dataclass(frozen=True, slots=True)
class NotificationId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> NotificationId:
        return cls(uuid.uuid4())

    @classmethod
    def from_string(cls, raw: str) -> NotificationId:
        return cls(uuid.UUID(raw))

    def __str__(self) -> str:
        return str(self.value)
