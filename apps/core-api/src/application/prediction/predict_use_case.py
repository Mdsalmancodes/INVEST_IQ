from datetime import date, timedelta

from src.application.prediction.build_dependencies import build_dependencies
from src.application.market_data.get_ohlcv_bars_use_case import GetOhlcvBarsUseCase
from src.domain.market_data.value_objects import Interval


class PredictUseCase:

    def __init__(self):
        (
            instrument_repo,
            ohlcv_repo,
            provider_router,
            validation_service,
        ) = build_dependencies()

        self.ohlcv_use_case = GetOhlcvBarsUseCase(
            instrument_repository=instrument_repo,
            ohlcv_bar_repository=ohlcv_repo,
            provider_router=provider_router,
            validation_service=validation_service,
        )

    async def execute(self, symbol: str):
        end = date.today()
        start = end - timedelta(days=30)

        result = await self.ohlcv_use_case.execute(
            symbol=symbol,
            interval=Interval.ONE_DAY,
            start=start,
            end=end,
        )

        bars = result.bars

        if not bars:
            return {"error": "No data available"}

        closes = [float(bar.close.amount) for bar in bars]

        latest = closes[-1]
        prev = closes[-2] if len(closes) > 1 else closes[-1]

        trend = "UP" if latest > prev else "DOWN"

        return {
            "symbol": symbol,
            "latest_price": latest,
            "previous_price": prev,
            "trend": trend,
            "data_completeness": result.data_completeness,
            "bars_used": len(bars),
        }