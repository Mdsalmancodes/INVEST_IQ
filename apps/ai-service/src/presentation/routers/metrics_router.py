"""metrics_router.py — the "Metrics" endpoint from the founder's Phase 7
API catalog. Reports real operational metrics derived from the Model
Registry (per-family trained-version counts, active-version presence) —
a genuine, if modest, JSON metrics surface rather than a full Prometheus
exposition format, since no metrics-collection library (prometheus-client)
is part of this phase's dependency set and core-api itself has no
existing `/metrics` endpoint to match a wire format against (confirmed via
a codebase search — this is a new, not a replicated, surface). Disclosed
in docs/phase-7/known-issues.md as a deliberately minimal-but-real
implementation, not a placeholder.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.application.ml.model_status_use_case import ModelFamilyStatus, ModelStatusUseCase
from src.presentation.dependencies.ml_use_cases import get_model_status_use_case

router = APIRouter(prefix="/api/v1/ml", tags=["metrics"])


class ModelFamilyMetric(BaseModel):
    family: str
    has_active_version: bool
    trained_version_count: int


class MlMetricsResponse(BaseModel):
    model_families: list[ModelFamilyMetric]
    total_trained_versions: int
    families_with_active_version: int


@router.get("/metrics", response_model=MlMetricsResponse)
async def get_ml_metrics(
    use_case: Annotated[ModelStatusUseCase, Depends(get_model_status_use_case)],
) -> MlMetricsResponse:
    statuses: tuple[ModelFamilyStatus, ...] = await use_case.execute()
    family_metrics = [
        ModelFamilyMetric(
            family=s.family,
            has_active_version=s.active_version is not None,
            trained_version_count=s.version_count,
        )
        for s in statuses
    ]
    return MlMetricsResponse(
        model_families=family_metrics,
        total_trained_versions=sum(m.trained_version_count for m in family_metrics),
        families_with_active_version=sum(1 for m in family_metrics if m.has_active_version),
    )
