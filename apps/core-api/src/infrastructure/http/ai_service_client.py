"""HttpAiServiceClient — implements
src.application.ai_proxy.ai_service_client.AiServiceClient
for AI_SERVICE_MODE=live.

Responsibilities:
- Route requests from core-api to ai-service.
- Attach the required X-Internal-Service-Token header.
- Forward ai-service response status codes unchanged.
- Forward ai-service JSON response bodies unchanged.
- Reuse an injected shared httpx.AsyncClient when available.
- Provide useful diagnostics for timeout, network, and unexpected errors.

The ML prediction endpoint can execute multiple CPU-heavy models
(LSTM, ARIMA, Prophet, Random Forest, XGBoost, FinBERT, SHAP).
Therefore the read timeout is intentionally longer than ordinary API
requests.
"""

from __future__ import annotations

import time
import traceback
from typing import Any

import httpx

from src.application.ai_proxy.ai_service_client import AiServiceResponse


class HttpAiServiceClient:
    """HTTP implementation of the AiServiceClient protocol."""

    def __init__(
        self,
        base_url: str,
        internal_service_token: str,
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_service_token = internal_service_token

        # Keep the configured timeout, but make sure the default for
        # the ML service is long enough for the six-model ensemble.
        self._timeout_seconds = timeout_seconds

        self._injected_client = client

    # ============================================================
    # HTTP TIMEOUT CONFIGURATION
    # ============================================================

    def _timeout(self) -> httpx.Timeout:
        """Return explicit HTTP timeout configuration.

        connect:
            Time allowed to establish the connection to ai-service.

        read:
            Time allowed while waiting for ai-service to produce the
            complete response. This is the important timeout for ML
            inference.

        write:
            Time allowed to send the request body.

        pool:
            Time allowed to obtain a connection from the shared pool.
        """

        return httpx.Timeout(
            connect=10.0,
            read=self._timeout_seconds,
            write=30.0,
            pool=10.0,
        )

    # ============================================================
    # HEADERS
    # ============================================================

    def _headers(self) -> dict[str, str]:
        """Headers required for core-api -> ai-service communication."""

        return {
            "X-Internal-Service-Token": self._internal_service_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ============================================================
    # INTERNAL HTTP REQUEST
    # ============================================================

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> AiServiceResponse:
        """
        Send exactly one HTTP request to ai-service.

        The ai-service response status code and JSON body are returned
        without transformation.

        Network failures are converted into proxy-level errors because
        no ai-service HTTP response exists in those situations.
        """

        url = f"{self._base_url}{path}"

        headers = self._headers()
        timeout = self._timeout()

        print("=" * 70)
        print("🚀 AI SERVICE REQUEST")
        print("METHOD:", method)
        print("URL:", url)
        print("PARAMS:", params)
        print("PAYLOAD:", json_body)
        print("CONNECT TIMEOUT:", timeout.connect)
        print("READ TIMEOUT:", timeout.read)
        print("WRITE TIMEOUT:", timeout.write)
        print("POOL TIMEOUT:", timeout.pool)
        print("=" * 70)

        started_at = time.perf_counter()

        try:
            # --------------------------------------------------------
            # USE SHARED CLIENT WHEN INJECTED
            # --------------------------------------------------------

            if self._injected_client is not None:
                response = await self._injected_client.request(
                    method=method,
                    url=url,
                    json=json_body,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )

            # --------------------------------------------------------
            # FALLBACK CLIENT
            # --------------------------------------------------------

            else:
                async with httpx.AsyncClient(
                    timeout=timeout
                ) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        json=json_body,
                        params=params,
                        headers=headers,
                    )

            elapsed = time.perf_counter() - started_at

            print("=" * 70)
            print("📡 AI SERVICE RESPONSE")
            print("STATUS:", response.status_code)
            print("TIME:", round(elapsed, 3), "seconds")
            print("CONTENT-TYPE:", response.headers.get("content-type"))
            print("BODY:", response.text)
            print("=" * 70)

            # --------------------------------------------------------
            # SAFE JSON DECODING
            # --------------------------------------------------------

            try:
                body = response.json()

            except ValueError:
                body = {
                    "error": response.text,
                    "status_code": response.status_code,
                }

            # --------------------------------------------------------
            # FORWARD AI-SERVICE RESPONSE
            # --------------------------------------------------------

            return AiServiceResponse(
                status_code=response.status_code,
                body=body,
            )

        # ============================================================
        # CONNECT TIMEOUT
        # ============================================================

        except httpx.ConnectTimeout as exc:
            elapsed = time.perf_counter() - started_at

            print("=" * 70)
            print("⏰ AI SERVICE CONNECT TIMEOUT")
            print("TYPE:", type(exc).__name__)
            print("REPR:", repr(exc))
            print("DETAILS:", str(exc))
            print("ELAPSED:", round(elapsed, 3), "seconds")
            print("URL:", url)
            print("=" * 70)

            return AiServiceResponse(
                status_code=504,
                body={
                    "error": "AI service connection timeout",
                    "details": repr(exc),
                },
            )

        # ============================================================
        # READ TIMEOUT
        # ============================================================

        except httpx.ReadTimeout as exc:
            elapsed = time.perf_counter() - started_at

            print("=" * 70)
            print("⏰ AI SERVICE READ TIMEOUT")
            print("TYPE:", type(exc).__name__)
            print("REPR:", repr(exc))
            print("DETAILS:", str(exc))
            print("ELAPSED:", round(elapsed, 3), "seconds")
            print("READ TIMEOUT:", self._timeout_seconds)
            print("URL:", url)
            print("=" * 70)

            return AiServiceResponse(
                status_code=504,
                body={
                    "error": "AI service read timeout",
                    "details": repr(exc),
                    "timeout_seconds": self._timeout_seconds,
                },
            )

        # ============================================================
        # OTHER HTTP TIMEOUTS
        # ============================================================

        except httpx.TimeoutException as exc:
            elapsed = time.perf_counter() - started_at

            print("=" * 70)
            print("⏰ AI SERVICE TIMEOUT")
            print("TYPE:", type(exc).__name__)
            print("REPR:", repr(exc))
            print("DETAILS:", str(exc))
            print("ELAPSED:", round(elapsed, 3), "seconds")
            print("URL:", url)
            print("=" * 70)

            return AiServiceResponse(
                status_code=504,
                body={
                    "error": "AI service timeout",
                    "details": repr(exc),
                },
            )

        # ============================================================
        # NETWORK / REQUEST ERROR
        # ============================================================

        except httpx.RequestError as exc:
            elapsed = time.perf_counter() - started_at

            print("=" * 70)
            print("🌐 AI SERVICE REQUEST ERROR")
            print("TYPE:", type(exc).__name__)
            print("REPR:", repr(exc))
            print("DETAILS:", str(exc))
            print("ELAPSED:", round(elapsed, 3), "seconds")
            print("URL:", url)
            print("=" * 70)

            return AiServiceResponse(
                status_code=503,
                body={
                    "error": "AI service unreachable",
                    "details": repr(exc),
                },
            )

        # ============================================================
        # UNEXPECTED ERROR
        # ============================================================

        except Exception as exc:
            elapsed = time.perf_counter() - started_at

            print("=" * 70)
            print("💥 UNEXPECTED AI SERVICE CLIENT ERROR")
            print("TYPE:", type(exc).__name__)
            print("REPR:", repr(exc))
            print("DETAILS:", str(exc))
            print("ELAPSED:", round(elapsed, 3), "seconds")
            print("URL:", url)
            print("TRACEBACK:")
            traceback.print_exc()
            print("=" * 70)

            return AiServiceResponse(
                status_code=500,
                body={
                    "error": "AI service failure",
                    "details": repr(exc),
                },
            )

    # ============================================================
    # ML — PREDICT
    # ============================================================

    async def predict(
        self,
        payload: dict[str, Any],
    ) -> AiServiceResponse:
        return await self._request(
            "POST",
            "/api/v1/ml/predict",
            json_body=payload,
        )

    # ============================================================
    # ML — RECOMMENDATION
    # ============================================================

    async def get_recommendation(
        self,
        symbol: str,
    ) -> AiServiceResponse:
        return await self._request(
            "GET",
            f"/api/v1/ml/recommendation/{symbol}",
        )

    # ============================================================
    # ML — FORECAST
    # ============================================================

    async def get_forecast(
        self,
        symbol: str,
        lookback_days: int | None,
    ) -> AiServiceResponse:
        params = (
            {"lookback_days": lookback_days}
            if lookback_days is not None
            else None
        )

        return await self._request(
            "GET",
            f"/api/v1/ml/forecast/{symbol}",
            params=params,
        )

    # ============================================================
    # ML — SENTIMENT
    # ============================================================

    async def analyze_sentiment(
        self,
        payload: dict[str, Any],
    ) -> AiServiceResponse:
        return await self._request(
            "POST",
            "/api/v1/ml/sentiment",
            json_body=payload,
        )

    # ============================================================
    # ML — PORTFOLIO RECOMMENDATION
    # ============================================================

    async def get_portfolio_recommendation(
        self,
        payload: dict[str, Any],
    ) -> AiServiceResponse:
        return await self._request(
            "POST",
            "/api/v1/ml/portfolio-recommendation",
            json_body=payload,
        )

    # ============================================================
    # ML — PREDICTION HISTORY
    # ============================================================

    async def get_prediction_history(
        self,
        symbol: str,
        limit: int | None,
    ) -> AiServiceResponse:
        params = (
            {"limit": limit}
            if limit is not None
            else None
        )

        return await self._request(
            "GET",
            f"/api/v1/ml/predictions/{symbol}/history",
            params=params,
        )

    # ============================================================
    # ML — MODEL STATUS
    # ============================================================

    async def get_model_status(self) -> AiServiceResponse:
        return await self._request(
            "GET",
            "/api/v1/ml/models/status",
        )

    # ============================================================
    # ML — METRICS
    # ============================================================

    async def get_metrics(self) -> AiServiceResponse:
        return await self._request(
            "GET",
            "/api/v1/ml/metrics",
        )

    # ============================================================
    # ML — TRAIN MODEL
    # ============================================================

    async def train_model(
        self,
        payload: dict[str, Any],
    ) -> AiServiceResponse:
        return await self._request(
            "POST",
            "/api/v1/ml/models/train",
            json_body=payload,
        )

    # ============================================================
    # ML — RETRAIN MODEL
    # ============================================================

    async def retrain_model(
        self,
        payload: dict[str, Any],
    ) -> AiServiceResponse:
        return await self._request(
            "POST",
            "/api/v1/ml/models/retrain",
            json_body=payload,
        )

    # ============================================================
    # ML — DELETE MODEL
    # ============================================================

    async def delete_model(
        self,
        model_version_id: str,
    ) -> AiServiceResponse:
        return await self._request(
            "DELETE",
            f"/api/v1/ml/models/{model_version_id}",
        )

    # ============================================================
    # PHASE 10 — PORTFOLIO INTELLIGENCE
    # ============================================================

    async def analyze_portfolio_intelligence(
        self,
        payload: dict[str, Any],
    ) -> AiServiceResponse:
        return await self._request(
            "POST",
            "/api/v1/portfolio-intelligence/analyze",
            json_body=payload,
        )

    # ============================================================
    # PHASE 10 — MONTE CARLO
    # ============================================================

    async def run_monte_carlo_simulation(
        self,
        payload: dict[str, Any],
    ) -> AiServiceResponse:
        return await self._request(
            "POST",
            "/api/v1/portfolio-intelligence/monte-carlo",
            json_body=payload,
        )