"""AiServiceClient Protocol — the AI Service integration port.

Per Document 3 §7.1: core-api is the only caller of ai-service; the AI
Service must never be directly exposed to end clients. This Protocol is
the seam the presentation-layer AI proxy router depends on (never a
concrete HTTP client directly), matching how market_data's
MarketDataProvider Protocol keeps use cases decoupled from a specific
vendor SDK (src/application/market_data/provider.py).

Deliberately passes through raw JSON-decoded dicts rather than a full
parallel set of Pydantic response models mirroring every ai-service DTO —
this proxy's job is authorization + routing, not reshaping ai-service's
already-well-defined response contracts (those are already fully typed
once, in ai-service's own src/presentation/dto/ml_dto.py, and again in
the frontend's lib/ai-api.ts; a third parallel Pydantic mirror here would
be pure duplication with no behavior of its own). The proxy router's own
response_model annotations still give FastAPI's OpenAPI generation
*something* concrete for the fields Phase 8 explicitly cares about
(status codes, error shapes) — see ai_proxy_router.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AiServiceResponse:
    """Wraps a successful ai-service response — the proxy layer forwards
    `status_code` so the router can mirror it back to the caller exactly
    (e.g. ai-service's 422 for insufficient data should surface as this
    proxy's 422 too, not get flattened to a generic 502)."""

    status_code: int
    body: dict[str, Any]


class AiServiceClient(Protocol):
    """Every method maps 1:1 to one of ai-service's existing
    /api/v1/ml/* endpoints (built Phase 7) — this Protocol adds no new
    ai-service capability, it only defines the shape core-api's proxy
    router depends on to reach the capabilities that already exist.
    """

    async def predict(self, payload: dict[str, Any]) -> AiServiceResponse: ...

    async def get_recommendation(self, symbol: str) -> AiServiceResponse: ...

    async def get_forecast(self, symbol: str, lookback_days: int | None) -> AiServiceResponse: ...

    async def analyze_sentiment(self, payload: dict[str, Any]) -> AiServiceResponse: ...

    async def get_portfolio_recommendation(self, payload: dict[str, Any]) -> AiServiceResponse: ...

    async def get_prediction_history(self, symbol: str, limit: int | None) -> AiServiceResponse: ...

    async def get_model_status(self) -> AiServiceResponse: ...

    async def get_metrics(self) -> AiServiceResponse: ...

    async def train_model(self, payload: dict[str, Any]) -> AiServiceResponse: ...

    async def retrain_model(self, payload: dict[str, Any]) -> AiServiceResponse: ...

    async def delete_model(self, model_version_id: str) -> AiServiceResponse: ...

    # --- Phase 10 (AI Portfolio Intelligence) — additive extension ---
    # Every method below maps 1:1 to one of ai-service's new
    # /api/v1/portfolio-intelligence/* endpoints (built Phase 10, see
    # docs/phase-10/implementation-summary.md), following the exact same
    # "map to an existing ai-service endpoint, add no new ai-service
    # capability here" contract as every method above.

    async def get_portfolio_analytics(self, payload: dict[str, Any]) -> AiServiceResponse: ...

    async def get_portfolio_risk_metrics(self, payload: dict[str, Any]) -> AiServiceResponse: ...

    async def get_ai_portfolio_predictions(
        self, payload: dict[str, Any]
    ) -> AiServiceResponse: ...

    async def run_monte_carlo_simulation(self, payload: dict[str, Any]) -> AiServiceResponse: ...

    async def get_portfolio_optimization(self, payload: dict[str, Any]) -> AiServiceResponse: ...

    async def get_portfolio_recommendations_v2(
        self, payload: dict[str, Any]
    ) -> AiServiceResponse: ...
