"""
Unit tests for PredictUseCase.

Infrastructure dependencies are replaced with deterministic fakes.

The purpose of these tests is to verify:

    real application orchestration
        ↓
    market data
        ↓
    symbol-specific ModelLoader
        ↓
    DecisionEngine
        ↓
    PredictionRun persistence
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ml.predict_use_case import (
    PredictUseCase,
)

from src.domain.ml.entities import (
    Forecast,
    HorizonPoint,
    Recommendation,
)

from src.domain.ml.value_objects import (
    Confidence,
    ExplainabilityPayload,
    ModelVersionId,
)

from tests.unit.application.ml._fixtures import (
    FakeMarketDataRepository,
    FakePredictionRunRepository,
    synthetic_bars,
)


# ============================================================================
# FAKE DECISION RESULT
# ============================================================================


@dataclass
class FakeDecisionResult:
    recommendation: Recommendation

    member_forecasts: tuple[
        Forecast,
        ...
    ]

    excluded_models: tuple[str, ...]

    price_forecast_1d: float

    price_forecast_7d: float

    price_forecast_30d: float


# ============================================================================
# FAKE DECISION ENGINE
# ============================================================================


class FakeDecisionEngine:

    def __init__(self) -> None:

        self.calls: list[dict] = []

    def decide(
        self,
        symbol: str,
        ohlcv,
        news_texts,
    ) -> FakeDecisionResult:

        self.calls.append(
            {
                "symbol": symbol,
                "rows": len(ohlcv),
                "news_texts": news_texts,
            }
        )

        current_price = float(
            ohlcv["close"].iloc[-1]
        )

        forecast_price = (
            current_price * 1.01
        )

        forecast = Forecast.create(
            symbol=symbol,

            model_family="arima",

            model_version_id=(
                ModelVersionId.new()
            ),

            points=(
                HorizonPoint(
                    horizon_days=1,
                    predicted_price=(
                        forecast_price
                    ),
                    lower_bound=(
                        current_price * 0.99
                    ),
                    upper_bound=(
                        current_price * 1.03
                    ),
                ),
            ),

            confidence=Confidence(
                0.80
            ),

            data_quality="full",
        )

        recommendation = (
            Recommendation.create(
                symbol=symbol,

                verdict="buy",

                confidence=Confidence(
                    0.80
                ),

                price_forecast=(
                    forecast_price
                ),

                sentiment_score=0.0,

                explainability=(
                    ExplainabilityPayload(
                        top_contributions=(),
                        base_value=(
                            current_price
                        ),
                        method="test",
                        reasoning=(
                            "Deterministic "
                            "unit-test "
                            "recommendation."
                        ),
                    )
                ),

                data_quality="full",

                contributing_models=(
                    "arima",
                ),
            )
        )

        return FakeDecisionResult(
            recommendation=recommendation,

            member_forecasts=(
                forecast,
            ),

            excluded_models=(),

            price_forecast_1d=(
                forecast_price
            ),

            price_forecast_7d=(
                forecast_price
            ),

            price_forecast_30d=(
                forecast_price
            ),
        )


# ============================================================================
# FAKE MODEL LOADER
# ============================================================================


class FakeModelLoader:

    def __init__(self) -> None:

        self.loaded_symbols: list[
            str
        ] = []

    async def load_all_models(
        self,
        symbol: str,
    ) -> dict:

        self.loaded_symbols.append(
            symbol
        )

        return {
            "lstm": object(),
            "arima": object(),
            "prophet": object(),
            "random_forest": object(),
            "xgboost": object(),
            "finbert": object(),
        }


# ============================================================================
# TESTS
# ============================================================================


class TestPredictUseCase:

    async def test_raises_when_no_bars_available(
        self,
    ) -> None:

        market_data_repo = (
            FakeMarketDataRepository
            .with_default_bars(())
        )

        prediction_repo = (
            FakePredictionRunRepository()
        )

        decision_engine = (
            FakeDecisionEngine()
        )

        model_loader = (
            FakeModelLoader()
        )

        use_case = PredictUseCase(
            market_data_repository=(
                market_data_repo
            ),
            prediction_run_repository=(
                prediction_repo
            ),
            decision_engine=(
                decision_engine
            ),
            model_loader=(
                model_loader
            ),
        )

        try:

            await use_case.execute(
                symbol="AAPL"
            )

            raise AssertionError(
                "Expected ValueError"
            )

        except ValueError as exc:

            assert (
                "No OHLCV market data"
                in str(exc)
            )

    async def test_loads_models_for_requested_symbol(
        self,
    ) -> None:

        market_data_repo = (
            FakeMarketDataRepository
            .with_default_bars(
                synthetic_bars(100)
            )
        )

        prediction_repo = (
            FakePredictionRunRepository()
        )

        decision_engine = (
            FakeDecisionEngine()
        )

        model_loader = (
            FakeModelLoader()
        )

        use_case = PredictUseCase(
            market_data_repository=(
                market_data_repo
            ),
            prediction_run_repository=(
                prediction_repo
            ),
            decision_engine=(
                decision_engine
            ),
            model_loader=(
                model_loader
            ),
        )

        result = await use_case.execute(
            symbol="aapl"
        )

        assert result is not None

        assert (
            model_loader.loaded_symbols
            == ["AAPL"]
        )

        assert (
            decision_engine.calls[0][
                "symbol"
            ]
            == "AAPL"
        )

    async def test_produces_and_persists_prediction(
        self,
    ) -> None:

        market_data_repo = (
            FakeMarketDataRepository
            .with_default_bars(
                synthetic_bars(100)
            )
        )

        prediction_repo = (
            FakePredictionRunRepository()
        )

        decision_engine = (
            FakeDecisionEngine()
        )

        model_loader = (
            FakeModelLoader()
        )

        use_case = PredictUseCase(
            market_data_repository=(
                market_data_repo
            ),
            prediction_run_repository=(
                prediction_repo
            ),
            decision_engine=(
                decision_engine
            ),
            model_loader=(
                model_loader
            ),
        )

        result = await use_case.execute(
            symbol="aapl"
        )

        assert (
            result.recommendation.symbol
            == "AAPL"
        )

        assert (
            result.recommendation.verdict
            == "buy"
        )

        assert (
            len(
                prediction_repo.saved
            )
            == 1
        )

        assert (
            prediction_repo.saved[0].symbol
            == "AAPL"
        )

    async def test_cleans_news_texts(
        self,
    ) -> None:

        market_data_repo = (
            FakeMarketDataRepository
            .with_default_bars(
                synthetic_bars(100)
            )
        )

        prediction_repo = (
            FakePredictionRunRepository()
        )

        decision_engine = (
            FakeDecisionEngine()
        )

        model_loader = (
            FakeModelLoader()
        )

        use_case = PredictUseCase(
            market_data_repository=(
                market_data_repo
            ),
            prediction_run_repository=(
                prediction_repo
            ),
            decision_engine=(
                decision_engine
            ),
            model_loader=(
                model_loader
            ),
        )

        await use_case.execute(
            symbol="AAPL",

            news_texts=[
                "  Strong earnings beat estimates.  ",
                "",
                "   ",
                "Revenue increased significantly.",
            ],
        )

        assert (
            decision_engine.calls[0][
                "news_texts"
            ]
            == [
                "Strong earnings beat estimates.",
                "Revenue increased significantly.",
            ]
        )