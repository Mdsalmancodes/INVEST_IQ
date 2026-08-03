"""Unit tests for HttpAiServiceClient — real httpx client roundtrip
against an httpx.MockTransport fixture (matching ai-service's own
test_market_data_repository.py's HttpMarketDataRepository test pattern:
a real client, a fake transport, not a mocked repository/client object).
"""

from __future__ import annotations

import httpx
import pytest

from src.infrastructure.http.ai_service_client import HttpAiServiceClient

_TOKEN = "test-shared-secret"


def _build_client(handler: httpx.MockTransport) -> HttpAiServiceClient:
    injected = httpx.AsyncClient(transport=handler)
    return HttpAiServiceClient(
        base_url="http://ai-service:8000",
        internal_service_token=_TOKEN,
        timeout_seconds=5.0,
        client=injected,
    )


class TestHttpAiServiceClient:
    async def test_predict_sends_the_internal_service_token_header(self) -> None:
        captured: dict[str, httpx.Request] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["request"] = request
            return httpx.Response(200, json={"symbol": "AAPL", "verdict": "buy"})

        client = _build_client(httpx.MockTransport(handler))

        result = await client.predict({"symbol": "AAPL"})

        assert result.status_code == 200
        assert result.body == {"symbol": "AAPL", "verdict": "buy"}
        assert captured["request"].headers["x-internal-service-token"] == _TOKEN
        assert captured["request"].url.path == "/api/v1/ml/predict"

    async def test_get_recommendation_calls_the_correct_path(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v1/ml/recommendation/AAPL"
            return httpx.Response(200, json={"symbol": "AAPL"})

        client = _build_client(httpx.MockTransport(handler))

        result = await client.get_recommendation("AAPL")

        assert result.status_code == 200

    async def test_get_forecast_forwards_lookback_days_as_a_query_param(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["lookback_days"] == "500"
            return httpx.Response(200, json={})

        client = _build_client(httpx.MockTransport(handler))

        await client.get_forecast("AAPL", 500)

    async def test_mirrors_a_non_200_status_code_from_ai_service(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"detail": "insufficient history"})

        client = _build_client(httpx.MockTransport(handler))

        result = await client.predict({"symbol": "ZZZZ"})

        assert result.status_code == 422
        assert result.body == {"detail": "insufficient history"}

    async def test_delete_model_handles_a_204_no_content_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "DELETE"
            return httpx.Response(204)

        client = _build_client(httpx.MockTransport(handler))

        result = await client.delete_model("11111111-1111-1111-1111-111111111111")

        assert result.status_code == 204
        assert result.body == {}

    async def test_train_model_sends_a_post_with_the_payload(self) -> None:
        captured: dict[str, httpx.Request] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["request"] = request
            return httpx.Response(200, json={"model_version": {}})

        client = _build_client(httpx.MockTransport(handler))

        await client.train_model({"family": "arima", "symbol": "AAPL"})

        assert captured["request"].method == "POST"
        assert captured["request"].url.path == "/api/v1/ml/train"


@pytest.mark.asyncio
async def test_client_without_an_injected_httpx_client_still_constructs() -> None:
    # Exercises the non-test code path (no injected client) purely for
    # construction — does not make a real network call.
    client = HttpAiServiceClient(
        base_url="http://ai-service:8000",
        internal_service_token=_TOKEN,
        timeout_seconds=5.0,
    )
    assert client is not None



class TestPortfolioIntelligenceMethods:
    async def test_analyze_portfolio_intelligence_calls_the_correct_path(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/api/v1/portfolio-intelligence/analyze"
            return httpx.Response(200, json={"analytics": {}})

        client = _build_client(httpx.MockTransport(handler))

        result = await client.analyze_portfolio_intelligence({"holdings": []})

        assert result.status_code == 200
        assert result.body == {"analytics": {}}

    async def test_run_monte_carlo_simulation_calls_the_correct_path(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/api/v1/portfolio-intelligence/monte-carlo"
            return httpx.Response(200, json={"num_runs": 100})

        client = _build_client(httpx.MockTransport(handler))

        result = await client.run_monte_carlo_simulation({"holdings": [], "num_runs": 100})

        assert result.status_code == 200
        assert result.body == {"num_runs": 100}
