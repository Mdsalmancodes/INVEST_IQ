from __future__ import annotations
import pandas as pd

class MockMarketDataRepository:

    async def get_ohlcv_bars(
        self,
        symbol: str,
        timeframe: str = "1d",
        lookback_days: int = 30,
    ) -> pd.DataFrame:

        # 🔥 Fake stock data (works for ML pipeline)
        data = {
            "open": [2500, 2510, 2520, 2530, 2540],
            "high": [2510, 2525, 2535, 2545, 2555],
            "low": [2490, 2505, 2515, 2525, 2535],
            "close": [2505, 2520, 2530, 2540, 2550],
            "volume": [100000, 120000, 110000, 130000, 125000],
        }

        return pd.DataFrame(data)