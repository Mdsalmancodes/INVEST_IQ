import pandas as pd
import yfinance as yf
from src.domain.ml.repositories import MarketDataRepository


class MockMarketDataRepository(MarketDataRepository):

    async def get_ohlcv_bars(self, symbol: str, lookback_days: int):

        df = yf.download(
            symbol,
            period="5y",        # 🔥 VERY IMPORTANT
            interval="1d"
        )

        # Standardize column names
        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })

        df = df[["open", "high", "low", "close", "volume"]]

        df.dropna(inplace=True)

        return df