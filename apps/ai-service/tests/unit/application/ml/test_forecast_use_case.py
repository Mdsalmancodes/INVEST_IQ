"""Unit tests for ForecastUseCase."""

from __future__ import annotations

import pytest

from src.application.ml.forecast_use_case import ForecastCommand, ForecastUseCase
from src.domain.ml.exceptions import InsufficientDataError
from tests.unit.application.ml._fixtures import FakeMarketDataRepository, synthetic_bars


class TestForecastUseCase:
    async def test_raises_when_no_bars_available(self) -> None:
        market_data_repo = FakeMarketDataRepository.with_default_bars(())
        use_case = ForecastUseCase(market_data_repo)

        with pytest.raises(InsufficientDataError, match="No OHLCV history"):
            await use_case.execute(ForecastCommand(symbol="AAPL"))

    async def test_runs_all_three_forecasting_models_with_sufficient_history(self) -> None:
        market_data_repo = FakeMarketDataRepository.with_default_bars(synthetic_bars(150))
        use_case = ForecastUseCase(market_data_repo)

        result = await use_case.execute(ForecastCommand(symbol="aapl"))

        assert result.symbol == "AAPL"
        families = {f.model_family for f in result.member_forecasts}
        assert families == {"lstm", "arima", "prophet"}
        assert result.excluded_models == ()

    async def test_excludes_lstm_and_prophet_below_their_thresholds(self) -> None:
        market_data_repo = FakeMarketDataRepository.with_default_bars(synthetic_bars(25))
        use_case = ForecastUseCase(market_data_repo)

        result = await use_case.execute(ForecastCommand(symbol="AAPL"))

        assert "lstm" in result.excluded_models
        assert "prophet" in result.excluded_models
        families = {f.model_family for f in result.member_forecasts}
        assert families == {"arima"}

    async def test_each_forecast_covers_1d_7d_and_30d_horizons(self) -> None:
        market_data_repo = FakeMarketDataRepository.with_default_bars(synthetic_bars(150))
        use_case = ForecastUseCase(market_data_repo)

        result = await use_case.execute(ForecastCommand(symbol="AAPL"))

        for forecast in result.member_forecasts:
            horizons = {p.horizon_days for p in forecast.points}
            assert horizons == {1, 7, 30}
