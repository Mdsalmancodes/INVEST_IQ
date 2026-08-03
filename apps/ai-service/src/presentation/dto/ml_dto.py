"""Pydantic request/response DTOs for the AI/ML bounded context's REST
API — mirrors core-api's presentation/dto/*.py decimal-as-string-for-
money discipline where applicable, and Document 4 §10.1's structural
invariant that every advisory response carries confidence + explainability
+ model version/data-quality information, never as optional fields.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.ml.value_objects import ModelFamily


class FeatureContributionResponse(BaseModel):
    name: str
    value: float
    direction: str


class ExplainabilityResponse(BaseModel):
    top_contributions: list[FeatureContributionResponse]
    base_value: float
    method: str
    reasoning: str


class HorizonPointResponse(BaseModel):
    horizon_days: int
    predicted_price: float
    lower_bound: float
    upper_bound: float


class MemberForecastResponse(BaseModel):
    model_family: str
    points: list[HorizonPointResponse]
    confidence: float
    data_quality: str


class MemberSignalResponse(BaseModel):
    model_family: str
    signal: float
    confidence: float
    weight: float


# --- Predict / Buy-Sell-Hold Recommendation ---


class PredictRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    # Same DoS-bound rationale as SentimentAnalysisRequest.texts above —
    # news_texts feeds the same synchronous FinBERT batch inference path
    # inside DecisionEngine.decide().
    news_texts: list[str] | None = Field(default=None, max_length=100)
    lookback_days: int = Field(default=400, ge=30, le=2000)


class RecommendationResponse(BaseModel):
    symbol: str
    verdict: str
    confidence: float = Field(..., description="Overall Confidence %, expressed as [0.0, 1.0]")
    price_forecast: float = Field(..., description="Final Price Forecast (next-day)")
    sentiment_score: float = Field(..., description="Market Sentiment Score, [-1.0, 1.0]")
    data_quality: str
    contributing_models: list[str]
    explainability: ExplainabilityResponse
    member_signals: list[MemberSignalResponse]
    excluded_models: list[str]
    price_forecast_7d: float
    price_forecast_30d: float


# --- Forecast ---


class ForecastRequest(BaseModel):
    lookback_days: int = Field(default=400, ge=30, le=2000)


class ForecastResponse(BaseModel):
    symbol: str
    member_forecasts: list[MemberForecastResponse]
    excluded_models: list[str]


# --- Sentiment Analysis ---


class SentimentAnalysisRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    # max_length bounds the batch size — unbounded lists here would let a
    # single request drive an arbitrarily large synchronous FinBERT batch
    # inference call (a DoS risk against this endpoint independent of the
    # asyncio.to_thread() event-loop fix in ml_router.py, which only stops
    # ONE such request from blocking OTHER requests — it doesn't bound how
    # much work any single request can demand).
    texts: list[str] = Field(..., min_length=1, max_length=100)


class SentimentItemResponse(BaseModel):
    label: str
    confidence: float
    source_text: str | None = None


class SentimentAnalysisResponse(BaseModel):
    symbol: str
    per_item_scores: list[SentimentItemResponse]
    aggregate_label: str
    aggregate_confidence: float
    aggregate_article_count: int


# --- Portfolio Recommendation ---


class PortfolioHoldingRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity: float = Field(..., gt=0)


class PortfolioRecommendationRequest(BaseModel):
    holdings: list[PortfolioHoldingRequest] = Field(..., min_length=1)
    lookback_days: int = Field(default=400, ge=30, le=2000)


class PortfolioRecommendationItemResponse(BaseModel):
    symbol: str
    quantity: float
    verdict: str
    confidence: float
    price_forecast: float


class PortfolioRecommendationResponse(BaseModel):
    items: list[PortfolioRecommendationItemResponse]
    overall_verdict: str
    overall_sentiment_score: float


# --- Prediction History ---


class PredictionRunResponse(BaseModel):
    id: str
    symbol: str
    ensemble_price: float
    ensemble_confidence: float
    data_quality: str
    created_at: str
    actual_price: float | None = None


class PredictionHistoryResponse(BaseModel):
    symbol: str
    items: list[PredictionRunResponse]


# --- Model Status ---


class ModelVersionResponse(BaseModel):
    id: str
    version_tag: str
    trained_at: str
    status: str
    validation_metrics: dict[str, float]
    artifact_location: str


class ModelFamilyStatusResponse(BaseModel):
    family: str
    active_version: ModelVersionResponse | None
    version_count: int


class ModelStatusResponse(BaseModel):
    families: list[ModelFamilyStatusResponse]


# --- Train / Retrain ---


class TrainModelRequest(BaseModel):
    family: ModelFamily
    symbol: str = Field(..., min_length=1, max_length=20)
    lookback_days: int = Field(default=400, ge=30, le=2000)


class TrainModelResponse(BaseModel):
    model_version: ModelVersionResponse
    validation_metrics: dict[str, float]
