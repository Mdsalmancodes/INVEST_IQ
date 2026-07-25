"""Domain entities for the AI/ML bounded context.

Per Document 4 §10.1's structural invariant: `Forecast` and `Recommendation`
require confidence + explainability + model version + dataQuality at
construction time — the constructor raises if any is missing, rather than
allowing an incomplete entity to exist and be discovered later. Mirrors
core-api's "aggregate owns its invariants" convention (Watchlist, Alert).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.domain.ml.value_objects import (
    Confidence,
    DataQuality,
    ExplainabilityPayload,
    ModelFamily,
    ModelVersionId,
    PredictionRunId,
    SentimentLabel,
    Verdict,
)


@dataclass(frozen=True, slots=True)
class HorizonPoint:
    """A single forecasted price point at a given horizon (Document 4
    §10.2's LSTM/ARIMA/Prophet output shape, normalized to one common
    entity so the decision engine can combine heterogeneous model outputs
    uniformly)."""

    horizon_days: int
    predicted_price: float
    lower_bound: float
    upper_bound: float


@dataclass(slots=True)
class Forecast:
    """A single model family's price forecast for one instrument —
    Document 4 §10.1's structural invariant applied: confidence,
    model_version_id, and data_quality are required constructor
    arguments, never optional/defaulted to a sentinel."""

    id: PredictionRunId
    symbol: str
    model_family: ModelFamily
    model_version_id: ModelVersionId
    points: tuple[HorizonPoint, ...]
    confidence: Confidence
    data_quality: DataQuality
    created_at: datetime

    @classmethod
    def create(
        cls,
        symbol: str,
        model_family: ModelFamily,
        model_version_id: ModelVersionId,
        points: tuple[HorizonPoint, ...],
        confidence: Confidence,
        data_quality: DataQuality,
    ) -> Forecast:
        if not points:
            raise ValueError("Forecast must contain at least one HorizonPoint")
        return cls(
            id=PredictionRunId.new(),
            symbol=symbol.upper(),
            model_family=model_family,
            model_version_id=model_version_id,
            points=points,
            confidence=confidence,
            data_quality=data_quality,
            created_at=datetime.now(UTC),
        )

    def point_for_horizon(self, horizon_days: int) -> HorizonPoint | None:
        for point in self.points:
            if point.horizon_days == horizon_days:
                return point
        return None


@dataclass(slots=True)
class PredictionRun:
    """The immutable record of a completed ensemble prediction run for one
    instrument — persists every member Forecast plus the combined
    ensemble outcome, per Document 4 §10.2 step 4 ('Immutable PredictionRun
    written ..., never overwritten'). `actual_price` is populated later by
    a backfill job (unbuilt this phase — disclosed in known-issues.md)."""

    id: PredictionRunId
    symbol: str
    member_forecasts: tuple[Forecast, ...]
    ensemble_price: float
    ensemble_confidence: Confidence
    data_quality: DataQuality
    explainability: ExplainabilityPayload
    created_at: datetime
    actual_price: float | None = field(default=None)

    @classmethod
    def create(
        cls,
        symbol: str,
        member_forecasts: tuple[Forecast, ...],
        ensemble_price: float,
        ensemble_confidence: Confidence,
        data_quality: DataQuality,
        explainability: ExplainabilityPayload,
    ) -> PredictionRun:
        if not member_forecasts:
            raise ValueError("PredictionRun requires at least one member Forecast")
        return cls(
            id=PredictionRunId.new(),
            symbol=symbol.upper(),
            member_forecasts=member_forecasts,
            ensemble_price=ensemble_price,
            ensemble_confidence=ensemble_confidence,
            data_quality=data_quality,
            explainability=explainability,
            created_at=datetime.now(UTC),
        )

    def record_actual_price(self, actual_price: float) -> None:
        """Called by the (currently unbuilt — see known-issues.md)
        backfill job once the target date passes, per Document 4 §10.2
        step 4's accuracy-tracking design."""
        self.actual_price = actual_price

    @property
    def absolute_error(self) -> float | None:
        if self.actual_price is None:
            return None
        return abs(self.actual_price - self.ensemble_price)


@dataclass(slots=True)
class SentimentScore:
    """A FinBERT-scored sentiment result for one text item (news headline,
    social post) or an aggregated rolling score for a symbol — Document 4
    §10.3's FinBERT scoring + aggregation steps. `article_count` drives the
    volume-weighted confidence formula from §10.3 when this represents an
    aggregate rather than a single item."""

    symbol: str
    label: SentimentLabel
    confidence: Confidence
    article_count: int
    created_at: datetime
    source_text: str | None = field(default=None)

    @classmethod
    def create(
        cls,
        symbol: str,
        label: SentimentLabel,
        confidence: Confidence,
        article_count: int = 1,
        source_text: str | None = None,
    ) -> SentimentScore:
        if article_count < 1:
            raise ValueError(f"article_count must be >= 1, got {article_count}")
        return cls(
            symbol=symbol.upper(),
            label=label,
            confidence=confidence,
            article_count=article_count,
            created_at=datetime.now(UTC),
            source_text=source_text,
        )

    @classmethod
    def aggregate(cls, symbol: str, scores: tuple[SentimentScore, ...]) -> SentimentScore:
        """Rolling aggregation per Document 4 §10.3 step 5: a
        volume-weighted average with confidence scaled by article volume
        (`min(1.0, article_count_7d / target_volume)`), not a naive mean
        of per-article confidences, so a single-article aggregate is
        honestly low-confidence rather than falsely certain."""
        if not scores:
            raise ValueError("Cannot aggregate an empty tuple of SentimentScore")

        target_volume = 10
        label_weights = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
        weighted_sum = sum(label_weights[s.label] * s.confidence.value for s in scores)
        net_score = weighted_sum / len(scores)

        if net_score > 0.15:
            aggregate_label: SentimentLabel = "positive"
        elif net_score < -0.15:
            aggregate_label = "negative"
        else:
            aggregate_label = "neutral"

        volume_confidence = min(1.0, len(scores) / target_volume)
        return cls.create(
            symbol=symbol,
            label=aggregate_label,
            confidence=Confidence(round(volume_confidence, 4)),
            article_count=len(scores),
        )


@dataclass(slots=True)
class Recommendation:
    """The Hybrid Decision Engine's output — Document 4 §10.4's
    Recommendation Synthesis layer combined with the founder's Phase 7
    instruction to weight-vote across all 6 model families (a superset of
    the architecture doc's rules+scoring synthesis, extended per explicit
    instruction to also incorporate the ML ensemble's own agreement, not
    just forecast direction/sentiment/technical/fundamental signals).

    Every field required at construction — Document 4 §10.1's invariant.
    """

    id: PredictionRunId
    symbol: str
    verdict: Verdict
    confidence: Confidence
    price_forecast: float
    sentiment_score: float
    explainability: ExplainabilityPayload
    data_quality: DataQuality
    contributing_models: tuple[ModelFamily, ...]
    created_at: datetime

    @classmethod
    def create(
        cls,
        symbol: str,
        verdict: Verdict,
        confidence: Confidence,
        price_forecast: float,
        sentiment_score: float,
        explainability: ExplainabilityPayload,
        data_quality: DataQuality,
        contributing_models: tuple[ModelFamily, ...],
    ) -> Recommendation:
        if not contributing_models:
            raise ValueError("Recommendation requires at least one contributing model")
        if not (-1.0 <= sentiment_score <= 1.0):
            raise ValueError(f"sentiment_score must be in [-1.0, 1.0], got {sentiment_score}")
        return cls(
            id=PredictionRunId.new(),
            symbol=symbol.upper(),
            verdict=verdict,
            confidence=confidence,
            price_forecast=price_forecast,
            sentiment_score=sentiment_score,
            explainability=explainability,
            data_quality=data_quality,
            contributing_models=contributing_models,
            created_at=datetime.now(UTC),
        )


ModelStatus = str  # "training" | "validating" | "canary" | "active" | "retired" — see ModelVersion


@dataclass(slots=True)
class ModelVersion:
    """Per Document 4 §10.8's ModelVersion entity — tracks a trained
    artifact's lifecycle. Canary/rollout_percentage fields are modeled per
    the frozen schema but the canary-promotion workflow itself is not
    exercised by this phase's application layer (disclosed in
    known-issues.md — single-instance local artifact storage, no
    multi-version traffic splitting yet)."""

    id: ModelVersionId
    family: ModelFamily
    version_tag: str
    trained_at: datetime
    training_data_range_start: datetime
    training_data_range_end: datetime
    validation_metrics: dict[str, float]
    status: str
    artifact_location: str
    rollout_percentage: int = field(default=100)

    @classmethod
    def create(
        cls,
        family: ModelFamily,
        version_tag: str,
        training_data_range_start: datetime,
        training_data_range_end: datetime,
        validation_metrics: dict[str, float],
        artifact_location: str,
    ) -> ModelVersion:
        return cls(
            id=ModelVersionId.new(),
            family=family,
            version_tag=version_tag,
            trained_at=datetime.now(UTC),
            training_data_range_start=training_data_range_start,
            training_data_range_end=training_data_range_end,
            validation_metrics=validation_metrics,
            status="active",
            artifact_location=artifact_location,
        )

    def retire(self) -> None:
        self.status = "retired"
