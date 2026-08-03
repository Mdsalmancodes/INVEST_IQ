"""Tests for SentimentStreamingService — same fake-AiServiceClient
convention as test_ai_prediction_streaming_service.py (this service
calls the exact same get_recommendation() method, just extracts the
sentiment_score field instead of publishing the whole body)."""

from __future__ import annotations

from typing import Any

from src.application.ai_proxy.ai_service_client import AiServiceResponse
from src.infrastructure.realtime import channels
from src.infrastructure.realtime.connection_manager import ConnectionManager
from src.infrastructure.realtime.sentiment_streaming_service import SentimentStreamingService


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
            symbol, AiServiceResponse(status_code=200, body={"sentiment_score": 0.0})
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
) -> SentimentStreamingService:
    return SentimentStreamingService(
        manager, broker, ai_client, poll_interval_seconds=30.0  # type: ignore[arg-type]
    )


class TestTick:
    async def test_publishes_nothing_when_no_client_is_subscribed_to_any_sentiment_topic(
        self,
    ) -> None:
        manager = ConnectionManager()
        broker = FakeRedisBroker()
        ai_client = FakeAiServiceClient()
        service = _build_service(manager, broker, ai_client)

        await service.tick()

        assert broker.published == []
        assert ai_client.calls == []

    async def test_publishes_the_sentiment_score_for_every_subscribed_symbol(self) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["sentiment:AAPL"])
        broker = FakeRedisBroker()
        ai_client = FakeAiServiceClient(
            {"AAPL": AiServiceResponse(status_code=200, body={"sentiment_score": 0.42})}
        )
        service = _build_service(manager, broker, ai_client)

        await service.tick()

        expected_channel = channels.sentiment_channel("AAPL")
        matching = [(c, p) for c, p in broker.published if c == expected_channel]
        assert len(matching) == 1
        _, payload = matching[0]
        assert payload == {"symbol": "AAPL", "sentiment_score": 0.42}

    async def test_a_non_200_response_is_not_published(self) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["sentiment:AAPL"])
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
        subscriptions.subscribe(["sentiment:AAPL", "sentiment:MSFT"])
        broker = FakeRedisBroker()
        ai_client = FakeAiServiceClient(
            {"MSFT": AiServiceResponse(status_code=200, body={"sentiment_score": -0.1})},
            raise_for_symbols={"AAPL"},
        )
        service = _build_service(manager, broker, ai_client)

        await service.tick()

        published_channels = {c for c, _ in broker.published}
        assert channels.sentiment_channel("MSFT") in published_channels
        assert channels.sentiment_channel("AAPL") not in published_channels

    async def test_non_sentiment_topics_are_ignored_when_determining_symbols_to_poll(
        self,
    ) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["quote:AAPL", "ai:AAPL"])
        broker = FakeRedisBroker()
        ai_client = FakeAiServiceClient()
        service = _build_service(manager, broker, ai_client)

        await service.tick()

        assert ai_client.calls == []
