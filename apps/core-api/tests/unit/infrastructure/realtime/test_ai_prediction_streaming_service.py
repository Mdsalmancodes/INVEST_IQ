"""Tests for AiPredictionStreamingService — real ConnectionManager, a
fake AiServiceClient matching test_ai_proxy_router.py's own
FakeAiServiceClient shape (extended here to support per-symbol
responses/failures, needed to test per-symbol isolation)."""

from __future__ import annotations

from typing import Any

from src.application.ai_proxy.ai_service_client import AiServiceResponse
from src.infrastructure.realtime import channels
from src.infrastructure.realtime.ai_prediction_streaming_service import (
    AiPredictionStreamingService,
)
from src.infrastructure.realtime.connection_manager import ConnectionManager


class FakeWebSocket:
    async def accept(self) -> None:
        pass

    async def send_json(self, message: dict[str, object]) -> None:
        pass


class FakeRedisBroker:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, object]]] = []

    async def publish(self, channel: str, payload: dict[str, object]) -> None:
        self.published.append((channel, payload))


class FakeAiServiceClient:
    """Per-symbol responses/failures, matching AiServiceClient's Protocol
    surface — only get_recommendation is exercised by this service, but
    every method is implemented to satisfy the Protocol structurally."""

    def __init__(
        self,
        responses_by_symbol: dict[str, AiServiceResponse] | None = None,
        raise_for_symbols: set[str] | None = None,
    ) -> None:
        self._responses_by_symbol = responses_by_symbol or {}
        self._raise_for_symbols = raise_for_symbols or set()
        self.calls: list[str] = []

    async def get_recommendation(self, symbol: str) -> AiServiceResponse:
        self.calls.append(symbol)
        if symbol in self._raise_for_symbols:
            raise RuntimeError("ai-service unreachable")
        return self._responses_by_symbol.get(
            symbol, AiServiceResponse(status_code=200, body={"symbol": symbol, "verdict": "hold"})
        )

    async def predict(self, payload: dict[str, Any]) -> AiServiceResponse:
        raise NotImplementedError

    async def get_forecast(self, symbol: str, lookback_days: int | None) -> AiServiceResponse:
        raise NotImplementedError

    async def analyze_sentiment(self, payload: dict[str, Any]) -> AiServiceResponse:
        raise NotImplementedError

    async def get_portfolio_recommendation(self, payload: dict[str, Any]) -> AiServiceResponse:
        raise NotImplementedError

    async def get_prediction_history(self, symbol: str, limit: int | None) -> AiServiceResponse:
        raise NotImplementedError

    async def get_model_status(self) -> AiServiceResponse:
        raise NotImplementedError

    async def get_metrics(self) -> AiServiceResponse:
        raise NotImplementedError

    async def train_model(self, payload: dict[str, Any]) -> AiServiceResponse:
        raise NotImplementedError

    async def retrain_model(self, payload: dict[str, Any]) -> AiServiceResponse:
        raise NotImplementedError

    async def delete_model(self, model_version_id: str) -> AiServiceResponse:
        raise NotImplementedError

    async def analyze_portfolio_intelligence(self, payload: dict[str, Any]) -> AiServiceResponse:
        raise NotImplementedError

    async def run_monte_carlo_simulation(self, payload: dict[str, Any]) -> AiServiceResponse:
        raise NotImplementedError


def _build_service(
    manager: ConnectionManager, broker: FakeRedisBroker, ai_client: FakeAiServiceClient
) -> AiPredictionStreamingService:
    return AiPredictionStreamingService(
        manager, broker, ai_client, poll_interval_seconds=30.0  # type: ignore[arg-type]
    )


class TestTick:
    async def test_publishes_nothing_when_no_client_is_subscribed_to_any_ai_topic(self) -> None:
        manager = ConnectionManager()
        broker = FakeRedisBroker()
        ai_client = FakeAiServiceClient()
        service = _build_service(manager, broker, ai_client)

        await service.tick()

        assert broker.published == []
        assert ai_client.calls == []

    async def test_publishes_the_recommendation_for_every_subscribed_symbol(self) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["ai:AAPL"])
        broker = FakeRedisBroker()
        ai_client = FakeAiServiceClient(
            {"AAPL": AiServiceResponse(status_code=200, body={"symbol": "AAPL", "verdict": "buy"})}
        )
        service = _build_service(manager, broker, ai_client)

        await service.tick()

        expected_channel = channels.ai_prediction_channel("AAPL")
        matching = [(c, p) for c, p in broker.published if c == expected_channel]
        assert len(matching) == 1
        _, payload = matching[0]
        assert payload == {"symbol": "AAPL", "verdict": "buy"}

    async def test_a_non_200_response_is_not_published_but_does_not_raise(self) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["ai:AAPL"])
        broker = FakeRedisBroker()
        ai_client = FakeAiServiceClient(
            {"AAPL": AiServiceResponse(status_code=422, body={"detail": "insufficient data"})}
        )
        service = _build_service(manager, broker, ai_client)

        await service.tick()

        assert broker.published == []

    async def test_a_failed_symbol_does_not_prevent_others_from_publishing(self) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["ai:AAPL", "ai:MSFT"])
        broker = FakeRedisBroker()
        ai_client = FakeAiServiceClient(
            {
                "MSFT": AiServiceResponse(
                    status_code=200, body={"symbol": "MSFT", "verdict": "sell"}
                )
            },
            raise_for_symbols={"AAPL"},
        )
        service = _build_service(manager, broker, ai_client)

        await service.tick()

        published_channels = {c for c, _ in broker.published}
        assert channels.ai_prediction_channel("MSFT") in published_channels
        assert channels.ai_prediction_channel("AAPL") not in published_channels

    async def test_non_ai_topics_are_ignored_when_determining_symbols_to_poll(self) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["quote:AAPL", "portfolio:abc"])
        broker = FakeRedisBroker()
        ai_client = FakeAiServiceClient()
        service = _build_service(manager, broker, ai_client)

        await service.tick()

        assert ai_client.calls == []
