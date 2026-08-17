from __future__ import annotations

import asyncio
import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, Query

# ============================================================================
# APPLICATION - USE CASES
# ============================================================================

from src.application.ml.forecast_use_case import (
    ForecastCommand,
    ForecastUseCase,
)

from src.application.ml.model_status_use_case import (
    ModelStatusUseCase,
)

from src.application.ml.portfolio_recommendation_use_case import (
    PortfolioHolding,
    PortfolioRecommendationCommand,
    PortfolioRecommendationUseCase,
)

from src.application.ml.predict_use_case import (
    PredictUseCase,
)

from src.application.ml.prediction_history_use_case import (
    PredictionHistoryQuery,
    PredictionHistoryUseCase,
)

from src.application.ml.sentiment_analysis_use_case import (
    SentimentAnalysisCommand,
    SentimentAnalysisUseCase,
)

from src.application.ml.train_model_use_case import (
    RetrainModelUseCase,
    TrainModelCommand,
    TrainModelResult,
    TrainModelUseCase,
)

# ============================================================================
# DOMAIN
# ============================================================================

from src.domain.ml.exceptions import (
    MlDomainError,
)

from src.domain.ml.value_objects import (
    ExplainabilityPayload,
)

# ============================================================================
# INFRASTRUCTURE
# ============================================================================

from src.infrastructure.http.market_data_repository import (
    MarketDataUnavailableError,
)

# ============================================================================
# DEPENDENCIES
# ============================================================================

from src.presentation.dependencies.ml_use_cases import (
    get_forecast_use_case,
    get_model_status_use_case,
    get_portfolio_recommendation_use_case,
    get_predict_use_case,
    get_prediction_history_use_case,
    get_retrain_model_use_case,
    get_sentiment_analysis_use_case,
    get_train_model_use_case,
)

# ============================================================================
# DTOs
# ============================================================================

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
    PredictRequest,
    PredictionHistoryResponse,
    PredictionRunResponse,
    RecommendationResponse,
    SentimentAnalysisRequest,
    SentimentAnalysisResponse,
    SentimentItemResponse,
    TrainModelRequest,
    TrainModelResponse,
)

# ============================================================================
# EXCEPTION HANDLER
# ============================================================================

from src.presentation.ml_exception_handlers import (
    raise_ml_exception_as_http,
)


# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(
    prefix="/api/v1/ml",
    tags=["ml"],
)


# ============================================================================
# HELPERS
# ============================================================================


def _enum_value(value):
    """
    Safely extract the underlying value from an Enum.

    If the object is not an Enum, return it unchanged.
    """

    return (
        value.value
        if hasattr(value, "value")
        else value
    )


def _raise_domain_exception_as_http(
    exc: Exception,
) -> None:
    """
    Convert known ML domain exceptions into HTTP exceptions.

    Unknown exceptions are re-raised unchanged.
    """

    if isinstance(exc, MlDomainError):
        raise_ml_exception_as_http(exc)

    raise exc


def _explainability_to_response(
    explainability: ExplainabilityPayload,
) -> ExplainabilityResponse:
    """
    Convert domain ExplainabilityPayload into
    the presentation/API response DTO.
    """

    return ExplainabilityResponse(
        top_contributions=[
            FeatureContributionResponse(
                name=contribution.name,
                value=float(contribution.value),
                direction=contribution.direction,
            )
            for contribution in explainability.top_contributions
        ],
        base_value=float(
            explainability.base_value
        ),
        method=explainability.method,
        reasoning=explainability.reasoning,
    )


def _decision_result_to_response(
    result,
) -> RecommendationResponse:
    """
    Convert PredictUseCase / DecisionEngine result
    into the public API response.
    """

    rec = result.recommendation

    confidence_value = (
        rec.confidence.value
        if hasattr(
            rec.confidence,
            "value",
        )
        else rec.confidence
    )

    return RecommendationResponse(
        symbol=rec.symbol,
        verdict=_enum_value(
            rec.verdict
        ),
        confidence=float(
            confidence_value
        ),
        price_forecast=float(
            rec.price_forecast
        ),
        sentiment_score=float(
            rec.sentiment_score
        ),
        data_quality=_enum_value(
            rec.data_quality
        ),
        contributing_models=[
            _enum_value(model)
            for model in rec.contributing_models
        ],
        explainability=_explainability_to_response(
            rec.explainability
        ),
        member_signals=[
            MemberSignalResponse(
                model_family=_enum_value(
                    signal.model_family
                ),
                signal=float(
                    signal.signal
                ),
                confidence=float(
                    signal.confidence
                ),
                weight=float(
                    signal.weight
                ),
            )
            for signal in result.member_signals
        ],
        excluded_models=[
            _enum_value(model)
            for model in result.excluded_models
        ],
        price_forecast_7d=float(
            result.price_forecast_7d
        ),
        price_forecast_30d=float(
            result.price_forecast_30d
        ),
    )


def _model_version_to_response(
    model_version,
) -> ModelVersionResponse:
    """
    Convert a domain ModelVersion entity into
    the public ModelVersionResponse DTO.
    """

    return ModelVersionResponse(
        id=str(
            model_version.id.value
        ),
        version_tag=model_version.version_tag,
        trained_at=model_version.trained_at.isoformat(),
        status=_enum_value(
            model_version.status
        ),
        artifact_location=model_version.artifact_location,
    )


def _train_result_to_response(
    result: TrainModelResult,
    message: str,
) -> TrainModelResponse:
    """
    Convert TrainModelResult into the public API response.
    """

    model_version = result.model_version

    return TrainModelResponse(
        success=True,
        message=message,
        model_version=_model_version_to_response(
            model_version
        ),
        validation_metrics={
            str(key): float(value)
            for key, value in result.validation_metrics.items()
        },
    )


# ============================================================================
# PREDICT
# ============================================================================


@router.post(
    "/predict",
    response_model=RecommendationResponse,
)
async def predict(
    body: PredictRequest,
    use_case: Annotated[
        PredictUseCase,
        Depends(get_predict_use_case),
    ],
) -> RecommendationResponse:

    try:
        print(
            "=============================================================="
        )
        print("🔥 PREDICT REQUEST")
        print("📌 INPUT:", body)

        clean_symbol = (
            body.symbol
            .upper()
            .strip()
        )

        if not clean_symbol:
            raise ValueError(
                "symbol must not be empty"
            )

        result = await use_case.execute(
            symbol=clean_symbol,
            news_texts=body.news_texts,
            lookback_days=body.lookback_days,
        )

        print(
            "🔥 RAW PREDICTION RESULT:",
            result,
        )

        response = _decision_result_to_response(
            result
        )

        print(
            "🔥 FINAL PREDICTION RESPONSE:",
            response,
        )

        print(
            "=============================================================="
        )

        return response

    except (
        MlDomainError,
        MarketDataUnavailableError,
    ) as exc:

        print(
            "❌ PREDICT DOMAIN ERROR:",
            str(exc),
        )

        _raise_domain_exception_as_http(exc)
        raise

    except Exception as exc:

        print(
            "💥 PREDICT UNEXPECTED ERROR:",
            str(exc),
        )

        traceback.print_exc()

        raise


# ============================================================================
# RECOMMENDATION
# ============================================================================


@router.get(
    "/recommendation/{symbol}",
    response_model=RecommendationResponse,
)
async def get_recommendation(
    symbol: str,
    use_case: Annotated[
        PredictUseCase,
        Depends(get_predict_use_case),
    ],
) -> RecommendationResponse:

    try:
        print(
            "=============================================================="
        )
        print(
            "🎯 RECOMMENDATION REQUEST:",
            symbol,
        )

        clean_symbol = (
            symbol
            .upper()
            .strip()
        )

        if not clean_symbol:
            raise ValueError(
                "symbol must not be empty"
            )

        result = await use_case.execute(
            symbol=clean_symbol,
            news_texts=[],
            lookback_days=400,
        )

        response = _decision_result_to_response(
            result
        )

        print(
            "🎯 RECOMMENDATION RESPONSE:",
            response,
        )

        print(
            "=============================================================="
        )

        return response

    except (
        MlDomainError,
        MarketDataUnavailableError,
    ) as exc:

        print(
            "❌ RECOMMENDATION DOMAIN ERROR:",
            str(exc),
        )

        _raise_domain_exception_as_http(exc)
        raise

    except Exception as exc:

        print(
            "💥 RECOMMENDATION ERROR:",
            str(exc),
        )

        traceback.print_exc()

        raise


# ============================================================================
# FORECAST
# ============================================================================


@router.get(
    "/forecast/{symbol}",
    response_model=ForecastResponse,
)
async def get_forecast(
    symbol: str,
    lookback_days: int = Query(
        default=400,
        ge=30,
        le=2000,
    ),
    use_case: Annotated[
        ForecastUseCase,
        Depends(get_forecast_use_case),
    ] = None,
) -> ForecastResponse:

    try:
        print(
            "=============================================================="
        )
        print("📈 FORECAST REQUEST")
        print("📌 SYMBOL:", symbol)
        print("📌 LOOKBACK DAYS:", lookback_days)

        clean_symbol = (
            symbol
            .upper()
            .strip()
        )

        if not clean_symbol:
            raise ValueError(
                "symbol must not be empty"
            )

        result = await use_case.execute(
            ForecastCommand(
                symbol=clean_symbol,
                lookback_days=lookback_days,
            )
        )

        print(
            "📈 FORECAST RAW RESULT:",
            result,
        )

        member_forecasts = []

        for forecast in result.member_forecasts:

            confidence_value = (
                forecast.confidence.value
                if hasattr(
                    forecast.confidence,
                    "value",
                )
                else forecast.confidence
            )

            points = []

            for point in forecast.points:

                points.append(
                    HorizonPointResponse(
                        horizon_days=int(
                            point.horizon_days
                        ),
                        predicted_price=float(
                            point.predicted_price
                        ),
                        lower_bound=float(
                            point.lower_bound
                        ),
                        upper_bound=float(
                            point.upper_bound
                        ),
                    )
                )

            member_forecasts.append(
                MemberForecastResponse(
                    model_family=_enum_value(
                        forecast.model_family
                    ),
                    points=points,
                    confidence=float(
                        confidence_value
                    ),
                    data_quality=_enum_value(
                        forecast.data_quality
                    ),
                )
            )

        response = ForecastResponse(
            symbol=result.symbol,
            member_forecasts=member_forecasts,
            excluded_models=[
                _enum_value(model)
                for model in result.excluded_models
            ],
        )

        print(
            "📈 FORECAST RESPONSE:",
            response,
        )

        print(
            "=============================================================="
        )

        return response

    except (
        MlDomainError,
        MarketDataUnavailableError,
    ) as exc:

        print(
            "❌ FORECAST DOMAIN ERROR:",
            str(exc),
        )

        _raise_domain_exception_as_http(exc)
        raise

    except Exception as exc:

        print(
            "💥 FORECAST ERROR:",
            str(exc),
        )

        traceback.print_exc()

        raise


# ============================================================================
# SENTIMENT ANALYSIS
# ============================================================================


@router.post(
    "/sentiment",
    response_model=SentimentAnalysisResponse,
)
async def analyze_sentiment(
    body: SentimentAnalysisRequest,
    use_case: Annotated[
        SentimentAnalysisUseCase,
        Depends(get_sentiment_analysis_use_case),
    ],
) -> SentimentAnalysisResponse:
    """
    Analyze financial/news sentiment using FinBERT.

    Flow:

        Request
            ↓
        SentimentAnalysisCommand
            ↓
        SentimentAnalysisUseCase
            ↓
        FinBertModel
            ↓
        per-item sentiment
            ↓
        aggregate sentiment
            ↓
        API response

    FinBERT inference is synchronous, therefore it is executed
    inside asyncio.to_thread() so the FastAPI event loop remains
    responsive.
    """

    try:
        print(
            "=============================================================="
        )
        print(
            "🧠 SENTIMENT ANALYSIS REQUEST:",
            body,
        )

        clean_symbol = (
            body.symbol
            .upper()
            .strip()
        )

        if not clean_symbol:
            raise ValueError(
                "symbol must not be empty"
            )

        command = SentimentAnalysisCommand(
            symbol=clean_symbol,
            texts=body.texts,
        )

        result = await asyncio.to_thread(
            use_case.execute,
            command,
        )

        print(
            "🧠 SENTIMENT ANALYSIS RESULT:",
            result,
        )

        response = SentimentAnalysisResponse(
            symbol=result.symbol,

            per_item_scores=[
                SentimentItemResponse(
                    label=_enum_value(
                        score.label
                    ),
                    confidence=float(
                        score.confidence.value
                    ),
                    source_text=score.source_text,
                )
                for score in result.per_item_scores
            ],

            aggregate_label=_enum_value(
                result.aggregate_score.label
            ),

            aggregate_confidence=float(
                result.aggregate_score.confidence.value
            ),

            aggregate_article_count=len(
                result.per_item_scores
            ),
        )

        print(
            "🧠 SENTIMENT ANALYSIS RESPONSE:",
            response,
        )

        print(
            "=============================================================="
        )

        return response

    except MlDomainError as exc:

        print(
            "❌ SENTIMENT DOMAIN ERROR:",
            str(exc),
        )

        _raise_domain_exception_as_http(exc)
        raise

    except Exception as exc:

        print(
            "💥 SENTIMENT ANALYSIS ERROR:",
            str(exc),
        )

        traceback.print_exc()

        raise


# ============================================================================
# PORTFOLIO RECOMMENDATION
# ============================================================================


@router.post(
    "/portfolio-recommendation",
    response_model=PortfolioRecommendationResponse,
)
async def portfolio_recommendation(
    body: PortfolioRecommendationRequest,
    use_case: Annotated[
        PortfolioRecommendationUseCase,
        Depends(
            get_portfolio_recommendation_use_case
        ),
    ],
) -> PortfolioRecommendationResponse:

    try:
        print(
            "=============================================================="
        )
        print(
            "💼 PORTFOLIO RECOMMENDATION REQUEST"
        )
        print(
            "📌 HOLDINGS:",
            body.holdings,
        )
        print(
            "📌 LOOKBACK DAYS:",
            body.lookback_days,
        )

        holdings = []

        for holding in body.holdings:

            clean_symbol = (
                holding.symbol
                .upper()
                .strip()
            )

            if not clean_symbol:
                raise ValueError(
                    "holding symbol must not be empty"
                )

            holdings.append(
                PortfolioHolding(
                    symbol=clean_symbol,
                    quantity=float(
                        holding.quantity
                    ),
                )
            )

        command = PortfolioRecommendationCommand(
            holdings=holdings,
            lookback_days=body.lookback_days,
        )

        result = await use_case.execute(
            command
        )

        print(
            "💼 PORTFOLIO RAW RESULT:",
            result,
        )

        items = []

        for item in result.items:

            recommendation = (
                item.decision.recommendation
            )

            confidence_value = (
                recommendation.confidence.value
                if hasattr(
                    recommendation.confidence,
                    "value",
                )
                else recommendation.confidence
            )

            items.append(
                PortfolioRecommendationItemResponse(
                    symbol=item.symbol,
                    quantity=float(
                        item.quantity
                    ),
                    verdict=_enum_value(
                        recommendation.verdict
                    ),
                    confidence=float(
                        confidence_value
                    ),
                    price_forecast=float(
                        recommendation.price_forecast
                    ),
                )
            )

        overall_verdict = _enum_value(
            result.overall_verdict
        )

        response = PortfolioRecommendationResponse(
            items=items,
            overall_verdict=overall_verdict,
            overall_sentiment_score=float(
                result.overall_sentiment_score
            ),
        )

        print(
            "💼 PORTFOLIO RECOMMENDATION RESPONSE:",
            response,
        )

        print(
            "=============================================================="
        )

        return response

    except (
        MlDomainError,
        MarketDataUnavailableError,
    ) as exc:

        print(
            "❌ PORTFOLIO RECOMMENDATION DOMAIN ERROR:",
            str(exc),
        )

        _raise_domain_exception_as_http(exc)
        raise

    except Exception as exc:

        print(
            "💥 PORTFOLIO RECOMMENDATION ERROR:",
            str(exc),
        )

        traceback.print_exc()

        raise


# ============================================================================
# PREDICTION HISTORY
# ============================================================================


@router.get(
    "/predictions/{symbol}/history",
    response_model=PredictionHistoryResponse,
)
async def get_prediction_history(
    symbol: str,
    use_case: Annotated[
        PredictionHistoryUseCase,
        Depends(get_prediction_history_use_case),
    ],
) -> PredictionHistoryResponse:

    try:
        print(
            "=============================================================="
        )
        print(
            "📜 PREDICTION HISTORY REQUEST:",
            symbol,
        )

        clean_symbol = (
            symbol
            .upper()
            .strip()
        )

        if not clean_symbol:
            raise ValueError(
                "symbol must not be empty"
            )

        query = PredictionHistoryQuery(
            symbol=clean_symbol,
            limit=20,
        )

        runs = await use_case.execute(
            query
        )

        print(
            "📜 PREDICTION HISTORY RECORDS:",
            len(runs),
        )

        items = [
            PredictionRunResponse(
                id=str(
                    run.id.value
                ),
                symbol=run.symbol,
                ensemble_price=float(
                    run.ensemble_price
                ),
                ensemble_confidence=float(
                    run.ensemble_confidence.value
                ),
                data_quality=_enum_value(
                    run.data_quality
                ),
                created_at=run.created_at.isoformat(),
                actual_price=(
                    float(run.actual_price)
                    if run.actual_price is not None
                    else None
                ),
            )
            for run in runs
        ]

        response = PredictionHistoryResponse(
            symbol=clean_symbol,
            items=items,
        )

        print(
            "📜 PREDICTION HISTORY RESPONSE:",
            response,
        )

        print(
            "=============================================================="
        )

        return response

    except (
        MlDomainError,
        MarketDataUnavailableError,
    ) as exc:

        print(
            "❌ PREDICTION HISTORY DOMAIN ERROR:",
            str(exc),
        )

        _raise_domain_exception_as_http(exc)
        raise

    except Exception as exc:

        print(
            "💥 PREDICTION HISTORY ERROR:",
            str(exc),
        )

        traceback.print_exc()

        raise


# ============================================================================
# MODEL STATUS
# ============================================================================


@router.get(
    "/models/status",
    response_model=ModelStatusResponse,
)
async def get_model_status(
    use_case: Annotated[
        ModelStatusUseCase,
        Depends(get_model_status_use_case),
    ],
) -> ModelStatusResponse:

    try:
        print(
            "=============================================================="
        )
        print(
            "📊 MODEL STATUS REQUEST"
        )

        statuses = await use_case.execute()

        families = [
            ModelFamilyStatusResponse(
                family=_enum_value(
                    status.family
                ),
                active_version=(
                    _model_version_to_response(
                        status.active_version
                    )
                    if status.active_version is not None
                    else None
                ),
                version_count=int(
                    status.version_count
                ),
            )
            for status in statuses
        ]

        response = ModelStatusResponse(
            families=families,
        )

        print(
            "📊 MODEL STATUS RESPONSE:",
            response,
        )

        print(
            "=============================================================="
        )

        return response

    except MlDomainError as exc:

        print(
            "❌ MODEL STATUS DOMAIN ERROR:",
            str(exc),
        )

        _raise_domain_exception_as_http(exc)
        raise

    except Exception as exc:

        print(
            "💥 MODEL STATUS ERROR:",
            str(exc),
        )

        traceback.print_exc()

        raise


# ============================================================================
# TRAIN MODEL
# ============================================================================


@router.post(
    "/models/train",
    response_model=TrainModelResponse,
)
async def train_model(
    body: TrainModelRequest,
    use_case: Annotated[
        TrainModelUseCase,
        Depends(get_train_model_use_case),
    ],
) -> TrainModelResponse:

    try:
        print(
            "=============================================================="
        )
        print(
            "🧠 TRAIN MODEL REQUEST"
        )
        print(
            "📌 FAMILY:",
            body.family,
        )
        print(
            "📌 SYMBOL:",
            body.symbol,
        )
        print(
            "📌 LOOKBACK:",
            body.lookback_days,
        )

        clean_symbol = (
            body.symbol
            .upper()
            .strip()
        )

        if not clean_symbol:
            raise ValueError(
                "symbol must not be empty"
            )

        result: TrainModelResult = (
            await use_case.execute(
                TrainModelCommand(
                    family=body.family,
                    symbol=clean_symbol,
                    lookback_days=body.lookback_days,
                )
            )
        )

        response = _train_result_to_response(
            result=result,
            message="Model trained successfully",
        )

        print(
            "🧠 TRAIN MODEL RESPONSE:",
            response,
        )

        print(
            "=============================================================="
        )

        return response

    except (
        MlDomainError,
        MarketDataUnavailableError,
    ) as exc:

        print(
            "❌ TRAIN MODEL DOMAIN ERROR:",
            str(exc),
        )

        _raise_domain_exception_as_http(exc)
        raise

    except Exception as exc:

        print(
            "💥 TRAIN MODEL ERROR:",
            str(exc),
        )

        traceback.print_exc()

        raise


# ============================================================================
# RETRAIN MODEL
# ============================================================================


@router.post(
    "/models/retrain",
    response_model=TrainModelResponse,
)
async def retrain_model(
    body: TrainModelRequest,
    use_case: Annotated[
        RetrainModelUseCase,
        Depends(get_retrain_model_use_case),
    ],
) -> TrainModelResponse:

    try:
        print(
            "=============================================================="
        )
        print(
            "🔄 RETRAIN MODEL REQUEST"
        )
        print(
            "📌 FAMILY:",
            body.family,
        )
        print(
            "📌 SYMBOL:",
            body.symbol,
        )
        print(
            "📌 LOOKBACK:",
            body.lookback_days,
        )

        clean_symbol = (
            body.symbol
            .upper()
            .strip()
        )

        if not clean_symbol:
            raise ValueError(
                "symbol must not be empty"
            )

        result: TrainModelResult = (
            await use_case.execute(
                TrainModelCommand(
                    family=body.family,
                    symbol=clean_symbol,
                    lookback_days=body.lookback_days,
                )
            )
        )

        response = _train_result_to_response(
            result=result,
            message="Model retrained successfully",
        )

        print(
            "🔄 RETRAIN MODEL RESPONSE:",
            response,
        )

        print(
            "=============================================================="
        )

        return response

    except (
        MlDomainError,
        MarketDataUnavailableError,
    ) as exc:

        print(
            "❌ RETRAIN MODEL DOMAIN ERROR:",
            str(exc),
        )

        _raise_domain_exception_as_http(exc)
        raise

    except Exception as exc:

        print(
            "💥 RETRAIN MODEL ERROR:",
            str(exc),
        )

        traceback.print_exc()

        raise