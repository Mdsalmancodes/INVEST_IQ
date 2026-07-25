"""ml_router.py — HTTP endpoints wiring all AI/ML use cases. Per the
founder's Phase 7 instruction, exposes: Train Models, Retrain Models,
Predict, Forecast, Sentiment Analysis, Portfolio Recommendation, Buy/
Sell/Hold Recommendation, Prediction History, Model Status (Health and
Metrics are separate routers — see health_router.py and metrics_router.py).

Every endpoint follows core-api's established pattern: build command/query
-> call use case -> map domain exceptions to HTTP -> return DTO.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.ml.decision_engine import DecisionEngineResult
from src.application.ml.delete_model_use_case import DeleteModelCommand, DeleteModelUseCase
from src.application.ml.forecast_use_case import ForecastCommand, ForecastResult, ForecastUseCase
from src.application.ml.model_status_use_case import ModelFamilyStatus, ModelStatusUseCase
from src.application.ml.portfolio_recommendation_use_case import (
    PortfolioHolding,
    PortfolioRecommendationCommand,
    PortfolioRecommendationResult,
    PortfolioRecommendationUseCase,
)
from src.application.ml.predict_use_case import PredictCommand, PredictUseCase
from src.application.ml.prediction_history_use_case import (
    PredictionHistoryQuery,
    PredictionHistoryUseCase,
)
from src.application.ml.sentiment_analysis_use_case import (
    SentimentAnalysisCommand,
    SentimentAnalysisResult,
    SentimentAnalysisUseCase,
)
from src.application.ml.train_model_use_case import (
    RetrainModelUseCase,
    TrainModelCommand,
    TrainModelResult,
    TrainModelUseCase,
)
from src.domain.ml.entities import ModelVersion, PredictionRun
from src.domain.ml.exceptions import MlDomainError
from src.domain.ml.value_objects import ExplainabilityPayload
from src.infrastructure.http.market_data_repository import MarketDataUnavailableError
from src.presentation.dependencies.ml_use_cases import (
    get_delete_model_use_case,
    get_forecast_use_case,
    get_model_status_use_case,
    get_portfolio_recommendation_use_case,
    get_predict_use_case,
    get_prediction_history_use_case,
    get_retrain_model_use_case,
    get_sentiment_analysis_use_case,
    get_train_model_use_case,
)
from src.presentation.dto.ml_dto import (
    ExplainabilityResponse,
    FeatureContributionResponse,
    ForecastResponse,
    HorizonPointResponse,
    MemberForecastResponse,
    MemberSignalResponse,
    ModelFamilyStatusResponse,
    ModelStatusResponse,
    ModelVersionResponse,
    PortfolioRecommendationItemResponse,
    PortfolioRecommendationRequest,
    PortfolioRecommendationResponse,
    PredictionHistoryResponse,
    PredictionRunResponse,
    PredictRequest,
    RecommendationResponse,
    SentimentAnalysisRequest,
    SentimentAnalysisResponse,
    SentimentItemResponse,
    TrainModelRequest,
    TrainModelResponse,
)
from src.presentation.ml_exception_handlers import raise_ml_exception_as_http

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])


def _raise_domain_exception_as_http(exc: Exception) -> None:
    if isinstance(exc, MlDomainError):
        raise_ml_exception_as_http(exc)
    raise exc


def _explainability_to_response(explainability: ExplainabilityPayload) -> ExplainabilityResponse:
    return ExplainabilityResponse(
        top_contributions=[
            FeatureContributionResponse(name=c.name, value=c.value, direction=c.direction)
            for c in explainability.top_contributions
        ],
        base_value=explainability.base_value,
        method=explainability.method,
        reasoning=explainability.reasoning,
    )


def _decision_result_to_response(result: DecisionEngineResult) -> RecommendationResponse:
    rec = result.recommendation
    return RecommendationResponse(
        symbol=rec.symbol,
        verdict=rec.verdict,
        confidence=rec.confidence.value,
        price_forecast=rec.price_forecast,
        sentiment_score=rec.sentiment_score,
        data_quality=rec.data_quality,
        contributing_models=list(rec.contributing_models),
        explainability=_explainability_to_response(rec.explainability),
        member_signals=[
            MemberSignalResponse(
                model_family=s.model_family, signal=s.signal, confidence=s.confidence,
                weight=s.weight,
            )
            for s in result.member_signals
        ],
        excluded_models=list(result.excluded_models),
        price_forecast_7d=result.price_forecast_7d,
        price_forecast_30d=result.price_forecast_30d,
    )


# --- Predict (also backs "Buy/Sell/Hold Recommendation") ---


@router.post("/predict", response_model=RecommendationResponse)
async def predict(
    body: PredictRequest,
    use_case: Annotated[PredictUseCase, Depends(get_predict_use_case)],
) -> RecommendationResponse:
    try:
        result = await use_case.execute(
            PredictCommand(
                symbol=body.symbol, news_texts=body.news_texts, lookback_days=body.lookback_days
            )
        )
    except (MlDomainError, MarketDataUnavailableError) as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return _decision_result_to_response(result)


@router.get("/recommendation/{symbol}", response_model=RecommendationResponse)
async def get_recommendation(
    symbol: str,
    use_case: Annotated[PredictUseCase, Depends(get_predict_use_case)],
) -> RecommendationResponse:
    """Buy/Sell/Hold Recommendation — identical computation to POST
    /predict (Recommendation.verdict IS the buy/sell/hold answer, per
    predict_use_case.py's module docstring); exposed as its own GET
    endpoint per the founder's explicit API catalog."""
    try:
        result = await use_case.execute(PredictCommand(symbol=symbol))
    except (MlDomainError, MarketDataUnavailableError) as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return _decision_result_to_response(result)


# --- Forecast ---


@router.get("/forecast/{symbol}", response_model=ForecastResponse)
async def get_forecast(
    symbol: str,
    use_case: Annotated[ForecastUseCase, Depends(get_forecast_use_case)],
    lookback_days: Annotated[int, Query(ge=30, le=2000)] = 400,
) -> ForecastResponse:
    try:
        result: ForecastResult = await use_case.execute(
            ForecastCommand(symbol=symbol, lookback_days=lookback_days)
        )
    except (MlDomainError, MarketDataUnavailableError) as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return ForecastResponse(
        symbol=result.symbol,
        member_forecasts=[
            MemberForecastResponse(
                model_family=f.model_family,
                points=[
                    HorizonPointResponse(
                        horizon_days=p.horizon_days,
                        predicted_price=p.predicted_price,
                        lower_bound=p.lower_bound,
                        upper_bound=p.upper_bound,
                    )
                    for p in f.points
                ],
                confidence=f.confidence.value,
                data_quality=f.data_quality,
            )
            for f in result.member_forecasts
        ],
        excluded_models=list(result.excluded_models),
    )


# --- Sentiment Analysis ---


@router.post("/sentiment", response_model=SentimentAnalysisResponse)
async def analyze_sentiment(
    body: SentimentAnalysisRequest,
    use_case: Annotated[SentimentAnalysisUseCase, Depends(get_sentiment_analysis_use_case)],
) -> SentimentAnalysisResponse:
    try:
        result: SentimentAnalysisResult = use_case.execute(
            SentimentAnalysisCommand(symbol=body.symbol, texts=body.texts)
        )
    except MlDomainError as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return SentimentAnalysisResponse(
        symbol=result.symbol,
        per_item_scores=[
            SentimentItemResponse(
                label=s.label, confidence=s.confidence.value, source_text=s.source_text
            )
            for s in result.per_item_scores
        ],
        aggregate_label=result.aggregate_score.label,
        aggregate_confidence=result.aggregate_score.confidence.value,
        aggregate_article_count=result.aggregate_score.article_count,
    )


# --- Portfolio Recommendation ---


@router.post("/portfolio-recommendation", response_model=PortfolioRecommendationResponse)
async def get_portfolio_recommendation(
    body: PortfolioRecommendationRequest,
    use_case: Annotated[
        PortfolioRecommendationUseCase, Depends(get_portfolio_recommendation_use_case)
    ],
) -> PortfolioRecommendationResponse:
    try:
        result: PortfolioRecommendationResult = await use_case.execute(
            PortfolioRecommendationCommand(
                holdings=[
                    PortfolioHolding(symbol=h.symbol, quantity=h.quantity)
                    for h in body.holdings
                ],
                lookback_days=body.lookback_days,
            )
        )
    except (MlDomainError, MarketDataUnavailableError) as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return PortfolioRecommendationResponse(
        items=[
            PortfolioRecommendationItemResponse(
                symbol=item.symbol,
                quantity=item.quantity,
                verdict=item.decision.recommendation.verdict,
                confidence=item.decision.recommendation.confidence.value,
                price_forecast=item.decision.recommendation.price_forecast,
            )
            for item in result.items
        ],
        overall_verdict=result.overall_verdict,
        overall_sentiment_score=result.overall_sentiment_score,
    )


# --- Prediction History ---


@router.get("/history/{symbol}", response_model=PredictionHistoryResponse)
async def get_prediction_history(
    symbol: str,
    use_case: Annotated[PredictionHistoryUseCase, Depends(get_prediction_history_use_case)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PredictionHistoryResponse:
    runs: tuple[PredictionRun, ...] = await use_case.execute(
        PredictionHistoryQuery(symbol=symbol, limit=limit)
    )
    return PredictionHistoryResponse(
        symbol=symbol.upper(),
        items=[
            PredictionRunResponse(
                id=str(run.id),
                symbol=run.symbol,
                ensemble_price=run.ensemble_price,
                ensemble_confidence=run.ensemble_confidence.value,
                data_quality=run.data_quality,
                created_at=run.created_at.isoformat(),
                actual_price=run.actual_price,
            )
            for run in runs
        ],
    )


# --- Model Status ---


def _model_version_to_response(version: ModelVersion) -> ModelVersionResponse:
    return ModelVersionResponse(
        id=str(version.id),
        version_tag=version.version_tag,
        trained_at=version.trained_at.isoformat(),
        status=version.status,
        validation_metrics=version.validation_metrics,
        artifact_location=version.artifact_location,
    )


@router.get("/models/status", response_model=ModelStatusResponse)
async def get_model_status(
    use_case: Annotated[ModelStatusUseCase, Depends(get_model_status_use_case)],
) -> ModelStatusResponse:
    statuses: tuple[ModelFamilyStatus, ...] = await use_case.execute()
    return ModelStatusResponse(
        families=[
            ModelFamilyStatusResponse(
                family=s.family,
                active_version=(
                    _model_version_to_response(s.active_version)
                    if s.active_version is not None
                    else None
                ),
                version_count=s.version_count,
            )
            for s in statuses
        ]
    )


@router.delete("/models/{model_version_id}", status_code=204, response_model=None)
async def delete_model(
    model_version_id: str,
    use_case: Annotated[DeleteModelUseCase, Depends(get_delete_model_use_case)],
) -> None:
    """Phase 8 addition — Admin-only 'Delete Models' requirement (enforced
    at core-api's proxy layer, not here — ai-service itself has no user/
    role concept; see docs/phase-8/known-issues.md for the disclosed
    boundary this implies)."""
    try:
        await use_case.execute(DeleteModelCommand(model_version_id=model_version_id))
    except MlDomainError as exc:
        _raise_domain_exception_as_http(exc)
        raise


# --- Train / Retrain ---


def _train_result_to_response(result: TrainModelResult) -> TrainModelResponse:
    return TrainModelResponse(
        model_version=_model_version_to_response(result.model_version),
        validation_metrics=result.validation_metrics,
    )


@router.post("/train", response_model=TrainModelResponse)
async def train_model(
    body: TrainModelRequest,
    use_case: Annotated[TrainModelUseCase, Depends(get_train_model_use_case)],
) -> TrainModelResponse:
    try:
        result = await use_case.execute(
            TrainModelCommand(
                family=body.family,  # type: ignore[arg-type]
                symbol=body.symbol,
                lookback_days=body.lookback_days,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (MlDomainError, MarketDataUnavailableError) as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return _train_result_to_response(result)


@router.post("/retrain", response_model=TrainModelResponse)
async def retrain_model(
    body: TrainModelRequest,
    use_case: Annotated[RetrainModelUseCase, Depends(get_retrain_model_use_case)],
) -> TrainModelResponse:
    try:
        result = await use_case.execute(
            TrainModelCommand(
                family=body.family,  # type: ignore[arg-type]
                symbol=body.symbol,
                lookback_days=body.lookback_days,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (MlDomainError, MarketDataUnavailableError) as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return _train_result_to_response(result)
