"""ai_proxy_router.py — the ONLY path by which any client of core-api can
reach ai-service's capabilities (Document 3 §7.1 / Phase 8's explicit "AI
Service must never be directly exposed" requirement). Every endpoint here:

1. Requires authentication (`Depends(get_current_user)`) — no AI capability
   is reachable anonymously, unlike ai-service's own /api/v1/ml/* surface
   which (by Phase 7 design, since ai-service has no user/role concept of
   its own) validates no bearer token at all.
2. For the 4 founder-named Admin-only actions (Train, Retrain, Delete,
   View Model Registry/Status) — additionally requires
   `Depends(require_role([Role.ADMIN, Role.SUPER_ADMIN]))`.
3. Forwards the request to ai-service via AiServiceClient (never a direct
   httpx call here — the router depends on the Protocol, matching every
   other router's use-case-Protocol pattern) and mirrors ai-service's own
   response status code and body back to the caller unmodified.

Registered under /api/v1/ai (a new prefix, distinct from ai-service's own
/api/v1/ml — this IS core-api's public-facing AI surface, ai-service's
/api/v1/ml is now an internal-only implementation detail behind it).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from src.application.ai_proxy.ai_service_client import AiServiceClient, AiServiceResponse
from src.application.auth.audit_logger import AuditLogger
from src.domain.auth.entities import Role
from src.presentation.dependencies.ai_proxy_use_cases import get_ai_service_client, get_audit_logger
from src.presentation.dependencies.auth import CurrentUser, get_current_user
from src.presentation.dependencies.rbac import require_role
from src.presentation.dto.ai_proxy_dto import (
    MonteCarloRequest,
    PortfolioIntelligenceRequest,
    PortfolioRecommendationRequest,
    PredictRequest,
    SentimentAnalysisRequest,
    TrainModelRequest,
)

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

_ADMIN_ROLES = [Role.ADMIN, Role.SUPER_ADMIN]


def _forward(response: Response, result: AiServiceResponse) -> dict[str, object]:
    response.status_code = result.status_code
    return result.body


@router.post("/predict")
async def predict(
    body: PredictRequest,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
) -> dict[str, object]:
    result = await client.predict(body.model_dump(exclude_none=True))
    return _forward(response, result)


@router.get("/recommendation/{symbol}")
async def get_recommendation(
    symbol: str,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
) -> dict[str, object]:
    result = await client.get_recommendation(symbol)
    return _forward(response, result)


@router.get("/forecast/{symbol}")
async def get_forecast(
    symbol: str,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
    lookback_days: Annotated[int | None, Query(ge=30, le=2000)] = None,
) -> dict[str, object]:
    result = await client.get_forecast(symbol, lookback_days)
    return _forward(response, result)


@router.post("/sentiment")
async def analyze_sentiment(
    body: SentimentAnalysisRequest,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
) -> dict[str, object]:
    result = await client.analyze_sentiment(body.model_dump())
    return _forward(response, result)


@router.post("/portfolio-recommendation")
async def get_portfolio_recommendation(
    body: PortfolioRecommendationRequest,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
) -> dict[str, object]:
    result = await client.get_portfolio_recommendation(body.model_dump())
    return _forward(response, result)


@router.post("/portfolio-intelligence/analyze")
async def analyze_portfolio_intelligence(
    body: PortfolioIntelligenceRequest,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
) -> dict[str, object]:
    """Phase 10 AI Portfolio Intelligence — Analytics, Risk Metrics, AI
    Portfolio Engine predictions, MPT Optimization, and the AI
    Recommendation Engine, all in one call (matching ai-service's own
    combined response shape). Authenticated like every other AI proxy
    endpoint above — not admin-only, since this is a user-facing
    portfolio insight feature, not a model-management action."""
    result = await client.analyze_portfolio_intelligence(body.model_dump())
    return _forward(response, result)


@router.post("/portfolio-intelligence/monte-carlo")
async def run_monte_carlo_simulation(
    body: MonteCarloRequest,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
) -> dict[str, object]:
    result = await client.run_monte_carlo_simulation(body.model_dump())
    return _forward(response, result)


@router.get("/history/{symbol}")
async def get_prediction_history(
    symbol: str,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> dict[str, object]:
    result = await client.get_prediction_history(symbol, limit)
    return _forward(response, result)


# --- Admin-only: Train Models, Retrain Models, Delete Models, View Model Registry ---


@router.get("/models/status")
async def get_model_status(
    response: Response,
    current_user: Annotated[CurrentUser, Depends(require_role(_ADMIN_ROLES))],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
) -> dict[str, object]:
    """Admin-only per the founder's explicit 'View Model Registry'
    requirement — a Basic/Premium user has no legitimate need to see
    which model versions are trained/active."""
    result = await client.get_model_status()
    return _forward(response, result)


@router.post("/models/train")
async def train_model(
    body: TrainModelRequest,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(require_role(_ADMIN_ROLES))],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
) -> dict[str, object]:
    result = await client.train_model(body.model_dump())
    await audit_logger.record(
        action="ai.model.train",
        user_id=current_user.user_id,
        resource_type="model_version",
        metadata={"family": body.family, "symbol": body.symbol, "status_code": result.status_code},
    )
    return _forward(response, result)


@router.post("/models/retrain")
async def retrain_model(
    body: TrainModelRequest,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(require_role(_ADMIN_ROLES))],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
) -> dict[str, object]:
    result = await client.retrain_model(body.model_dump())
    await audit_logger.record(
        action="ai.model.retrain",
        user_id=current_user.user_id,
        resource_type="model_version",
        metadata={"family": body.family, "symbol": body.symbol, "status_code": result.status_code},
    )
    return _forward(response, result)


@router.delete("/models/{model_version_id}")
async def delete_model(
    model_version_id: str,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(require_role(_ADMIN_ROLES))],
    client: Annotated[AiServiceClient, Depends(get_ai_service_client)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
) -> dict[str, object]:
    result = await client.delete_model(model_version_id)
    await audit_logger.record(
        action="ai.model.delete",
        user_id=current_user.user_id,
        resource_type="model_version",
        resource_id=model_version_id,
        metadata={"status_code": result.status_code},
    )
    return _forward(response, result)
