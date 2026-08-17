"""Unit tests for AiPortfolioEngineService — Phase 10 AI Portfolio Engine."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from src.application.portfolio_intelligence.ai_portfolio_engine_service import (
    AiPortfolioEngineService,
)
from src.application.portfolio_intelligence.analytics_service import (
    AnalyticsService,
)
from src.application.portfolio_intelligence.data import (
    PortfolioHoldingInput,
    fetch_holdings_returns,
)
from src.application.portfolio_intelligence.risk_metrics_service import (
    RiskMetricsService,
)
from src.infrastructure.ml.model_registry.model_loader import (
    LoadedModels,
)
from tests.unit.application.ml._fixtures import (
    FakeMarketDataRepository,
    synthetic_bars,
)


# ============================================================================
# DETERMINISTIC MODEL MOCKS
# ============================================================================


def _mock_lstm(
    change: float = 1.0,
) -> MagicMock:
    """
    Create a deterministic LSTM mock.

    DecisionEngine expects:

        predict_next(close_history, steps_ahead=30)

    returning a sequence of future prices.
    """

    model = MagicMock(name="LSTM")

    model.predict_next.side_effect = (
        lambda history, steps_ahead=30: [
            float(
                history[-1]
                + change * (index + 1)
            )
            for index in range(
                steps_ahead
            )
        ]
    )

    return model


def _mock_arima(
    change: float = 0.5,
) -> MagicMock:
    """
    Create a deterministic ARIMA mock.
    """

    model = MagicMock(name="ARIMA")

    model.predict_next.side_effect = (
        lambda steps_ahead=30: [
            float(
                100.0
                + change * (index + 1)
            )
            for index in range(
                steps_ahead
            )
        ]
    )

    return model


def _mock_prophet(
    start_price: float = 100.0,
    change: float = 0.1,
) -> MagicMock:
    """
    Create a deterministic Prophet mock.
    """

    model = MagicMock(name="Prophet")

    model.predict_next.side_effect = (
        lambda steps_ahead=30: [
            float(
                start_price
                + change * (index + 1)
            )
            for index in range(
                steps_ahead
            )
        ]
    )

    return model


def _mock_random_forest(
    buy_probability: float = 0.65,
) -> MagicMock:
    """
    Create a deterministic Random Forest mock.

    DecisionEngine expects:

        predict_movement(feature_row)

    returning an array-like buy probability.
    """

    model = MagicMock(
        name="RandomForest"
    )

    model.predict_movement.return_value = np.array(
        [buy_probability],
        dtype=float,
    )

    return model


def _mock_xgboost(
    buy_probability: float = 0.65,
    sell_probability: float = 0.20,
) -> MagicMock:
    """
    Create a deterministic XGBoost mock.

    DecisionEngine expects:

        predict_buy_sell_probabilities(feature_row)

    returning:

        buy_probability_array,
        sell_probability_array
    """

    model = MagicMock(
        name="XGBoost"
    )

    model.predict_buy_sell_probabilities.return_value = (
        np.array(
            [buy_probability],
            dtype=float,
        ),
        np.array(
            [sell_probability],
            dtype=float,
        ),
    )

    return model


def _mock_finbert(
    label: str = "positive",
    confidence: float = 0.90,
) -> MagicMock:
    """
    Create a deterministic FinBERT mock.
    """

    model = MagicMock(
        name="FinBERT"
    )

    result = MagicMock()

    result.label = label
    result.confidence = confidence

    model.analyze_batch.return_value = [
        result
    ]

    return model


# ============================================================================
# FAKE MODEL LOADER
# ============================================================================


class FakeModelLoader:
    """
    Deterministic ModelLoader replacement for unit tests.

    The real ModelLoader loads trained artifacts from the model registry.

    This fake deliberately avoids filesystem/database/model-artifact
    dependencies while still exposing the exact interface required by
    AiPortfolioEngineService.
    """

    def __init__(self) -> None:
        self.loaded_symbols: list[str] = []

    async def load_all_models(
        self,
        symbol: str,
    ) -> LoadedModels:
        self.loaded_symbols.append(
            symbol
        )

        return LoadedModels(
            models={
                "lstm": _mock_lstm(),
                "arima": _mock_arima(),
                "prophet": _mock_prophet(),
                "random_forest": _mock_random_forest(),
                "xgboost": _mock_xgboost(),
                "finbert": _mock_finbert(),
            },
            model_version_ids={},
        )


# ============================================================================
# TEST DATA BUNDLE
# ============================================================================


async def _build_bundle(
    holdings: list[PortfolioHoldingInput],
) -> tuple:
    """
    Build deterministic portfolio data for the tests.
    """

    bars_by_symbol = {
        holding.symbol: synthetic_bars(
            120,
            seed=hash(
                holding.symbol
            )
            % 1000,
        )
        for holding in holdings
    }

    repository = FakeMarketDataRepository(
        bars_by_symbol=bars_by_symbol,
    )

    data = await fetch_holdings_returns(
        repository,
        holdings,
    )

    analytics = AnalyticsService().compute(
        data
    )

    risk_metrics = RiskMetricsService().compute(
        data
    )

    return (
        data,
        analytics,
        risk_metrics,
        bars_by_symbol,
    )


# ============================================================================
# TEST CLASS
# ============================================================================


class TestAiPortfolioEngineService:
    """
    Unit tests for Phase 10 AiPortfolioEngineService.
    """

    # ========================================================================
    # FULL PORTFOLIO PREDICTION
    # ========================================================================

    async def test_computes_a_full_prediction_set_for_a_multi_holding_portfolio(
        self,
    ) -> None:
        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=1000.0,
                sector="Tech",
            ),
            PortfolioHoldingInput(
                symbol="MSFT",
                quantity=5,
                market_value=500.0,
                sector="Tech",
            ),
        ]

        (
            data,
            analytics,
            risk_metrics,
            bars_by_symbol,
        ) = await _build_bundle(
            holdings
        )

        model_loader = FakeModelLoader()

        service = AiPortfolioEngineService(
            model_loader=model_loader,
        )

        result = await service.compute(
            data,
            analytics,
            risk_metrics,
            bars_by_symbol,
        )

        assert (
            0.0
            <= result.portfolio_risk_prediction
            <= 100.0
        )

        assert (
            0.0
            <= result.investment_health_prediction
            <= 100.0
        )

        assert (
            0.0
            <= result.market_exposure_pct
            <= 100.0
        )

        assert (
            0.0
            <= result.portfolio_stability_score
            <= 100.0
        )

        assert (
            0.0
            <= result.portfolio_confidence_score
            <= 100.0
        )

        assert (
            len(result.sector_risk)
            == 1
        )

        assert (
            result.sector_risk[0].sector
            == "Tech"
        )

        # Both portfolio holdings should have requested
        # their symbol-specific models.
        assert set(
            model_loader.loaded_symbols
        ) == {
            "AAPL",
            "MSFT",
        }

    # ========================================================================
    # MARKET EXPOSURE
    # ========================================================================

    async def test_market_exposure_defaults_to_a_neutral_midpoint_with_no_beta(
        self,
    ) -> None:
        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=1000.0,
                sector="Tech",
            )
        ]

        (
            data,
            analytics,
            risk_metrics,
            bars_by_symbol,
        ) = await _build_bundle(
            holdings
        )

        service = AiPortfolioEngineService(
            model_loader=FakeModelLoader(),
        )

        result = await service.compute(
            data,
            analytics,
            risk_metrics,
            bars_by_symbol,
        )

        # No benchmark was supplied to RiskMetricsService.compute(),
        # therefore beta is None.
        #
        # Phase 10 explicitly defines 50.0 as the neutral midpoint.
        assert (
            result.market_exposure_pct
            == 50.0
        )

    # ========================================================================
    # MISSING MARKET DATA
    # ========================================================================

    async def test_a_holding_missing_from_bars_by_symbol_is_excluded_without_error(
        self,
    ) -> None:
        holdings = [
            PortfolioHoldingInput(
                symbol="AAPL",
                quantity=10,
                market_value=1000.0,
                sector="Tech",
            )
        ]

        (
            data,
            analytics,
            risk_metrics,
            _,
        ) = await _build_bundle(
            holdings
        )

        model_loader = FakeModelLoader()

        service = AiPortfolioEngineService(
            model_loader=model_loader,
        )

        # Deliberately provide no OHLCV bars.
        #
        # AiPortfolioEngineService must skip the holding instead of
        # attempting DecisionEngine inference without market data.
        result = await service.compute(
            data,
            analytics,
            risk_metrics,
            {},
        )

        assert (
            result.expected_return_pct
            == 0.0
        )

        assert (
            result.portfolio_confidence_score
            == 0.0
        )

        assert (
            result.portfolio_stability_score
            == 0.0
        )

        # Because no valid bars were available, ModelLoader should
        # never have been invoked.
        assert (
            model_loader.loaded_symbols
            == []
        )

    # ========================================================================
    # EMPTY PORTFOLIO
    # ========================================================================

    async def test_empty_holdings_produce_a_well_formed_zeroed_result(
        self,
    ) -> None:
        (
            data,
            analytics,
            risk_metrics,
            bars_by_symbol,
        ) = await _build_bundle(
            []
        )

        model_loader = FakeModelLoader()

        service = AiPortfolioEngineService(
            model_loader=model_loader,
        )

        result = await service.compute(
            data,
            analytics,
            risk_metrics,
            bars_by_symbol,
        )

        assert (
            result.expected_return_pct
            == 0.0
        )

        assert (
            result.portfolio_confidence_score
            == 0.0
        )

        assert (
            result.portfolio_stability_score
            == 0.0
        )

        assert (
            result.sector_risk
            == ()
        )

        # Empty portfolio means no model should be loaded.
        assert (
            model_loader.loaded_symbols
            == []
        )