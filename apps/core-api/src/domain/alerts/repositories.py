"""Repository interface (Protocol) for the alerts bounded context.

Per docs/architecture/02-clean-architecture-folder-frontend.md §4.1: these
live in the domain layer and are implemented by infrastructure — the
dependency arrow always points inward. Application-layer use cases depend
on this Protocol, never on a concrete SQLAlchemy implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from src.domain.alerts.entities import Alert
from src.domain.alerts.value_objects import AlertId, InstrumentId

AlertSortField = Literal["created_at", "threshold"]
SortDirection = Literal["asc", "desc"]


@dataclass(frozen=True, slots=True)
class AlertListFilter:
    """Filter/pagination/sort parameters for ListAlerts — matches
    Watchlist's WatchlistListFilter pattern (plain domain-layer dataclass,
    not Pydantic, which belongs to the presentation layer)."""

    is_active: bool | None = None
    """None means "no filter" (both active and inactive returned)."""
    sort_by: AlertSortField = "created_at"
    sort_direction: SortDirection = "desc"
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class AlertPageResult:
    items: tuple[Alert, ...]
    total_count: int
    page: int
    page_size: int


class AlertRepository(Protocol):
    async def save(self, alert: Alert) -> None:
        """Insert or update the Alert row — upsert semantics, matching
        Watchlist/PortfolioRepository.save() convention."""
        ...

    async def get_by_id(self, alert_id: AlertId) -> Alert | None: ...

    async def list_for_user(self, user_id: str, filters: AlertListFilter) -> AlertPageResult: ...

    async def list_active_for_instrument(self, instrument_id: InstrumentId) -> tuple[Alert, ...]:
        """Used by the alert evaluation engine — every active alert
        currently watching a given instrument, regardless of owning user,
        so a single price update can be checked against all matching
        alerts in one query."""
        ...

    async def delete(self, alert_id: AlertId) -> None: ...

    async def exists_duplicate(
        self,
        user_id: str,
        instrument_id: InstrumentId,
        condition_type: str,
        threshold: object,
        exclude_alert_id: AlertId | None = None,
    ) -> bool:
        """Application-layer defense-in-depth check mirroring the DB's
        uq_alerts_duplicate UNIQUE constraint, matching how
        CreateWatchlistUseCase pre-checks the default-watchlist invariant
        before relying solely on a DB-level guarantee."""
        ...
