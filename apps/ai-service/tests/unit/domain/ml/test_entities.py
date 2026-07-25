"""Unit tests for the AI/ML domain entities."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.domain.ml.entities import (
    Forecast,
    HorizonPoint,
    ModelVersion,
    PredictionRun,
    Recommendation,
    SentimentScore,
)
from src.domain.ml.value_objects import (
    Confidence,
    ExplainabilityPayload,
    FeatureContribution,
    ModelVersionId,
)


def _explainability() -> ExplainabilityPayload:
    return ExplainabilityPayload(
        top_contributions=(FeatureContribution(name="rsi14", value=0.12),),
        base_value=0.5,
        method="shap_tree_explainer",
        reasoning="RSI oversold contributed positively.",
    )


def _single_point() -> tuple[HorizonPoint, ...]:
    return (HorizonPoint(horizon_days=1, predicted_price=150.0, lower_bound=145, upper_bound=155),)


class TestConfidence:
    def test_accepts_boundary_values(self) -> None:
        assert Confidence(0.0).value == 0.0
        assert Confidence(1.0).value == 1.0

    def test_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="must be in"):
            Confidence(1.5)
        with pytest.raises(ValueError, match="must be in"):
            Confidence(-0.1)

    def test_as_percentage(self) -> None:
        assert Confidence(0.876).as_percentage() == 87.6


class TestExplainabilityPayload:
    def test_rejects_more_than_8_contributions(self) -> None:
        contributions = tuple(FeatureContribution(name=f"f{i}", value=0.1) for i in range(9))
        with pytest.raises(ValueError, match="capped at 8"):
            ExplainabilityPayload(
                top_contributions=contributions,
                base_value=0.0,
                method="shap",
                reasoning="test",
            )


class TestForecastCreate:
    def test_creates_with_required_fields(self) -> None:
        forecast = Forecast.create(
            symbol="aapl",
            model_family="lstm",
            model_version_id=ModelVersionId.new(),
            points=_single_point(),
            confidence=Confidence(0.8),
            data_quality="full",
        )
        assert forecast.symbol == "AAPL"
        assert forecast.model_family == "lstm"
        assert forecast.data_quality == "full"

    def test_rejects_empty_points(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            Forecast.create(
                symbol="AAPL",
                model_family="arima",
                model_version_id=ModelVersionId.new(),
                points=(),
                confidence=Confidence(0.5),
                data_quality="full",
            )

    def test_point_for_horizon_returns_matching_point(self) -> None:
        forecast = Forecast.create(
            symbol="AAPL",
            model_family="lstm",
            model_version_id=ModelVersionId.new(),
            points=(
                HorizonPoint(
                    horizon_days=1, predicted_price=150.0, lower_bound=145, upper_bound=155
                ),
                HorizonPoint(
                    horizon_days=7, predicted_price=155.0, lower_bound=140, upper_bound=170
                ),
            ),
            confidence=Confidence(0.8),
            data_quality="full",
        )
        point = forecast.point_for_horizon(7)
        assert point is not None
        assert point.predicted_price == 155.0

    def test_point_for_horizon_returns_none_when_missing(self) -> None:
        forecast = Forecast.create(
            symbol="AAPL",
            model_family="lstm",
            model_version_id=ModelVersionId.new(),
            points=_single_point(),
            confidence=Confidence(0.8),
            data_quality="full",
        )
        assert forecast.point_for_horizon(30) is None


class TestPredictionRunCreate:
    def _forecast(self) -> Forecast:
        return Forecast.create(
            symbol="AAPL",
            model_family="lstm",
            model_version_id=ModelVersionId.new(),
            points=_single_point(),
            confidence=Confidence(0.8),
            data_quality="full",
        )

    def test_creates_with_member_forecasts(self) -> None:
        run = PredictionRun.create(
            symbol="aapl",
            member_forecasts=(self._forecast(),),
            ensemble_price=151.0,
            ensemble_confidence=Confidence(0.75),
            data_quality="full",
            explainability=_explainability(),
        )
        assert run.symbol == "AAPL"
        assert run.actual_price is None
        assert run.absolute_error is None

    def test_rejects_empty_member_forecasts(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            PredictionRun.create(
                symbol="AAPL",
                member_forecasts=(),
                ensemble_price=150.0,
                ensemble_confidence=Confidence(0.5),
                data_quality="full",
                explainability=_explainability(),
            )

    def test_record_actual_price_computes_absolute_error(self) -> None:
        run = PredictionRun.create(
            symbol="AAPL",
            member_forecasts=(self._forecast(),),
            ensemble_price=150.0,
            ensemble_confidence=Confidence(0.75),
            data_quality="full",
            explainability=_explainability(),
        )
        run.record_actual_price(155.0)
        assert run.actual_price == 155.0
        assert run.absolute_error == 5.0


class TestSentimentScoreCreate:
    def test_creates_single_item_score(self) -> None:
        score = SentimentScore.create(symbol="aapl", label="positive", confidence=Confidence(0.9))
        assert score.symbol == "AAPL"
        assert score.article_count == 1

    def test_rejects_zero_article_count(self) -> None:
        with pytest.raises(ValueError, match="article_count must be"):
            SentimentScore.create(
                symbol="AAPL", label="positive", confidence=Confidence(0.9), article_count=0
            )


class TestSentimentScoreAggregate:
    def test_aggregates_mostly_positive_scores(self) -> None:
        scores = tuple(
            SentimentScore.create(symbol="AAPL", label="positive", confidence=Confidence(0.9))
            for _ in range(5)
        )
        aggregate = SentimentScore.aggregate("AAPL", scores)
        assert aggregate.label == "positive"
        assert aggregate.article_count == 5

    def test_low_volume_yields_low_confidence(self) -> None:
        scores = (
            SentimentScore.create(symbol="AAPL", label="positive", confidence=Confidence(0.95)),
        )
        aggregate = SentimentScore.aggregate("AAPL", scores)
        # 1 article / target_volume(10) = 0.1 confidence — honestly low, not falsely certain.
        assert aggregate.confidence.value == pytest.approx(0.1)

    def test_high_volume_caps_confidence_at_one(self) -> None:
        scores = tuple(
            SentimentScore.create(symbol="AAPL", label="positive", confidence=Confidence(0.9))
            for _ in range(20)
        )
        aggregate = SentimentScore.aggregate("AAPL", scores)
        assert aggregate.confidence.value == 1.0

    def test_mixed_scores_average_to_neutral(self) -> None:
        scores = (
            SentimentScore.create(symbol="AAPL", label="positive", confidence=Confidence(0.5)),
            SentimentScore.create(symbol="AAPL", label="negative", confidence=Confidence(0.5)),
        )
        aggregate = SentimentScore.aggregate("AAPL", scores)
        assert aggregate.label == "neutral"

    def test_rejects_empty_scores(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            SentimentScore.aggregate("AAPL", ())


class TestRecommendationCreate:
    def test_creates_with_required_fields(self) -> None:
        rec = Recommendation.create(
            symbol="aapl",
            verdict="buy",
            confidence=Confidence(0.8),
            price_forecast=155.0,
            sentiment_score=0.3,
            explainability=_explainability(),
            data_quality="full",
            contributing_models=("lstm", "xgboost", "finbert"),
        )
        assert rec.symbol == "AAPL"
        assert rec.verdict == "buy"

    def test_rejects_empty_contributing_models(self) -> None:
        with pytest.raises(ValueError, match="at least one contributing model"):
            Recommendation.create(
                symbol="AAPL",
                verdict="hold",
                confidence=Confidence(0.5),
                price_forecast=150.0,
                sentiment_score=0.0,
                explainability=_explainability(),
                data_quality="full",
                contributing_models=(),
            )

    def test_rejects_out_of_range_sentiment_score(self) -> None:
        with pytest.raises(ValueError, match="sentiment_score must be"):
            Recommendation.create(
                symbol="AAPL",
                verdict="hold",
                confidence=Confidence(0.5),
                price_forecast=150.0,
                sentiment_score=1.5,
                explainability=_explainability(),
                data_quality="full",
                contributing_models=("finbert",),
            )


class TestModelVersionCreate:
    def test_creates_as_active(self) -> None:
        version = ModelVersion.create(
            family="xgboost",
            version_tag="v1",
            training_data_range_start=datetime(2024, 1, 1, tzinfo=UTC),
            training_data_range_end=datetime(2024, 12, 31, tzinfo=UTC),
            validation_metrics={"rmse": 1.23, "directional_accuracy": 0.58},
            artifact_location="/models/xgboost/v1.joblib",
        )
        assert version.status == "active"
        assert version.rollout_percentage == 100

    def test_retire_changes_status(self) -> None:
        version = ModelVersion.create(
            family="lstm",
            version_tag="v1",
            training_data_range_start=datetime(2024, 1, 1, tzinfo=UTC),
            training_data_range_end=datetime(2024, 12, 31, tzinfo=UTC),
            validation_metrics={},
            artifact_location="/models/lstm/v1.pt",
        )
        version.retire()
        assert version.status == "retired"
