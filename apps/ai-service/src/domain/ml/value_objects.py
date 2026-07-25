"""Value objects for the AI/ML bounded context.

Per Document 4 §10.1's invariant: no model output reaches a user without a
confidence score, an explainability payload, a model version tag, and a
tracked dataQuality state — these value objects exist to make that
invariant structural (self-validating dataclasses), matching core-api's
domain-layer value object convention (see e.g.
apps/core-api/src/domain/watchlist/value_objects.py).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

ModelFamily = Literal["lstm", "arima", "prophet", "random_forest", "xgboost", "finbert"]
"""Per the founder's Phase 7 instruction: exactly these 6 model families,
never replaced, never removed, never substituted with a different model."""

DataQuality = Literal["full", "insufficientHistory", "partialEnsemble"]
"""Per Document 4 §10.1a — a disclosed reliability state, not a bypass of
the confidence/explainability invariant. 'partialEnsemble' covers both the
minimum-data-threshold exclusions in §10.1a AND a model family being
unavailable in the current runtime environment (e.g. Prophet without a
CmdStan backend — see known-issues.md), which is the same category of
"gracefully exclude, don't fail the whole request" handling."""

Verdict = Literal["buy", "sell", "hold"]

SentimentLabel = Literal["positive", "negative", "neutral"]


@dataclass(frozen=True, slots=True)
class Confidence:
    """A confidence score in [0.0, 1.0], self-validating per Document 4
    §10.1's structural invariant (never an optional/nullable field on any
    entity that carries one)."""

    value: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.value <= 1.0):
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {self.value}")

    def as_percentage(self) -> float:
        return round(self.value * 100, 2)


@dataclass(frozen=True, slots=True)
class PredictionRunId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> PredictionRunId:
        return cls(uuid.uuid4())

    @classmethod
    def from_string(cls, raw: str) -> PredictionRunId:
        return cls(uuid.UUID(raw))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class ModelVersionId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> ModelVersionId:
        return cls(uuid.uuid4())

    @classmethod
    def from_string(cls, raw: str) -> ModelVersionId:
        return cls(uuid.UUID(raw))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class FeatureContribution:
    """A single named feature's contribution to a model's output — the
    atomic unit of an ExplainabilityPayload (SHAP output), per Document 4
    §10.9's ShapExplainerService.explain() contract."""

    name: str
    value: float

    @property
    def direction(self) -> Literal["positive", "negative"]:
        return "positive" if self.value >= 0 else "negative"


@dataclass(frozen=True, slots=True)
class ExplainabilityPayload:
    """Per Document 4 §10.9 — every Recommendation/PredictionRun carries
    one of these. `top_contributions` is capped at 8 for UI readability,
    matching the architecture doc's own ShapExplainerService.explain()
    example exactly."""

    top_contributions: tuple[FeatureContribution, ...]
    base_value: float
    method: str
    reasoning: str

    def __post_init__(self) -> None:
        if len(self.top_contributions) > 8:
            raise ValueError(
                f"top_contributions must be capped at 8 for UI readability, "
                f"got {len(self.top_contributions)}"
            )
