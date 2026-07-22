"""Repository interfaces (Protocols) for the portfolio bounded context.

Per docs/architecture/02-clean-architecture-folder-frontend.md §4.1: these
live in the domain layer and are implemented by infrastructure — the
dependency arrow always points inward. Application-layer use cases depend on
these Protocols, never on a concrete SQLAlchemy implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.domain.portfolio.entities import Portfolio, Transaction, TransactionType
from src.domain.portfolio.value_objects import InstrumentId, PortfolioId, TransactionId


@dataclass(frozen=True, slots=True)
class TransactionFilter:
    """Filter/pagination parameters for ListTransactions — kept as a plain
    domain-layer dataclass (not a Pydantic model, which belongs to the
    presentation layer per Document 2 §4.1) so the Protocol below has no
    framework dependency."""

    instrument_id: InstrumentId | None = None
    types: tuple[TransactionType, ...] | None = None
    executed_after: datetime | None = None
    executed_before: datetime | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class PageResult:
    """Generic pagination envelope returned by repository list methods."""

    items: tuple[Transaction, ...]
    total_count: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class PortfolioListFilter:
    is_paper: bool | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class PortfolioPageResult:
    items: tuple[Portfolio, ...]
    total_count: int
    page: int
    page_size: int


class PortfolioRepository(Protocol):
    async def save(self, portfolio: Portfolio) -> None:
        """Insert or update the Portfolio row AND persist any Holding rows
        currently attached to `portfolio.holdings` (upsert semantics) —
        the aggregate root's save() is the only write path, matching
        Document 3 §3.4 rule #1 at the persistence boundary too."""
        ...

    async def get_by_id(self, portfolio_id: PortfolioId) -> Portfolio | None:
        """Loads the Portfolio WITH its holdings populated (the aggregate
        must be loaded whole, never partially, to keep apply_transaction's
        invariants meaningful)."""
        ...

    async def list_for_user(
        self, user_id: str, filters: PortfolioListFilter
    ) -> PortfolioPageResult: ...

    async def delete(self, portfolio_id: PortfolioId) -> None: ...

    async def exists_with_name_for_user(self, user_id: str, name: str) -> bool: ...


class TransactionRepository(Protocol):
    async def save(self, transaction: Transaction) -> None:
        """Transactions are append-only (Document 3 §3.4) — this always
        inserts, never updates an existing row."""
        ...

    async def get_by_id(self, transaction_id: TransactionId) -> Transaction | None: ...

    async def list_for_portfolio(
        self, portfolio_id: PortfolioId, filters: TransactionFilter
    ) -> PageResult: ...

    async def list_all_for_portfolio_unpaginated(
        self, portfolio_id: PortfolioId
    ) -> tuple[Transaction, ...]:
        """Used by the calculation service (realized gain, dividend income,
        etc.) which needs the full transaction history, not a page of it."""
        ...
