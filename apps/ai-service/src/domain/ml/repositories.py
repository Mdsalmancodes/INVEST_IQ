"""Repository interfaces (Protocols) for the AI/ML bounded context.

Per docs/architecture/02-clean-architecture-folder-frontend.md §4.1: these
live in the domain layer and are implemented by infrastructure — the
dependency arrow always points inward. Application-layer use cases and
model wrappers depend on these Protocols, never on a concrete HTTP client
or filesystem implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from src.domain.ml.entities import ModelVersion, PredictionRun
from src.domain.ml.value_objects import ModelFamily, ModelVersionId, PredictionRunId


@dataclass(frozen=True, slots=True)
class OhlcvBar:
    """Domain-layer OHLCV bar shape — deliberately independent of
    core-api's own OhlcvBarResponse DTO shape (the HTTP infrastructure
    layer maps between them), so this bounded context's domain model does
    not leak a dependency on core-api's wire format."""

    bar_time: datetime
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


class MarketDataRepository(Protocol):
    """Per the founder's Phase 7 instruction: 'Reuse the existing Market
    Data module. Reuse existing OHLCV tables... Never duplicate data.'
    Implemented in infrastructure as an HTTP client against core-api's
    already-public GET /api/v1/instruments/{symbol}/bars endpoint — this
    bounded context never opens its own Postgres connection or duplicates
    the ohlcv_bars table, per that explicit instruction.
    """

    async def get_ohlcv_bars(
        self, symbol: str, start: date, end: date, interval: str = "1d"
    ) -> tuple[OhlcvBar, ...]: ...


class ModelRegistryRepository(Protocol):
    """Per Document 4 §10.8's ModelVersion entity — tracks trained model
    artifacts and their lifecycle. Implemented in infrastructure as a
    local-filesystem-backed registry this phase (disclosed in
    known-issues.md — no S3-compatible object storage is available in
    this environment; the frozen architecture's artifact_location field
    is populated with a local path, and the abstraction is designed so
    swapping to real object storage later is an infrastructure-only
    change, never a domain-layer one)."""

    async def save(self, model_version: ModelVersion) -> None: ...

    async def get_by_id(self, model_version_id: ModelVersionId) -> ModelVersion | None: ...

    async def get_active_for_family(self, family: ModelFamily) -> ModelVersion | None: ...

    async def list_for_family(self, family: ModelFamily) -> tuple[ModelVersion, ...]: ...

    async def delete(self, model_version_id: ModelVersionId) -> bool:
        """Per Phase 8's Admin-only 'Delete Models' requirement — removes a
        trained version's tracking record. Returns True if a record was
        found and deleted, False if no matching version existed (so the
        application layer can distinguish "already gone" from a genuine
        failure without needing a separate exists() call)."""
        ...


class PredictionRunRepository(Protocol):
    """Per Document 4 §10.2 step 4: 'Immutable PredictionRun written ...,
    never overwritten.' Implemented in infrastructure this phase as a
    local-filesystem JSON-lines store (disclosed in known-issues.md — the
    frozen architecture specifies MongoDB for this collection, but no
    Mongo connection is configured in ai-service's config.py yet; this is
    the same category of 'infrastructure abstraction ready, real backing
    store deferred' decision already used for ModelRegistryRepository)."""

    async def save(self, prediction_run: PredictionRun) -> None: ...

    async def get_by_id(self, prediction_run_id: PredictionRunId) -> PredictionRun | None: ...

    async def list_for_symbol(
        self, symbol: str, limit: int = 20
    ) -> tuple[PredictionRun, ...]: ...
