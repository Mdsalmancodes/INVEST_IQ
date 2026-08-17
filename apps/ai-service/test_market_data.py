import asyncio
from datetime import date, timedelta

from src.infrastructure.http.market_data_repository import (
    MarketDataRepository,
)


async def main() -> None:
    repository = MarketDataRepository()

    end = date.today()
    start = end - timedelta(days=400)

    print("=" * 70)
    print("INVEST IQ - MARKET DATA REPOSITORY TEST")
    print("=" * 70)
    print(f"Symbol : AAPL")
    print(f"Start  : {start}")
    print(f"End    : {end}")
    print()

    bars = await repository.get_ohlcv_bars(
        "AAPL",
        start,
        end,
    )

    print(f"REPOSITORY BARS: {len(bars)}")

    if not bars:
        raise RuntimeError(
            "MarketDataRepository returned ZERO bars"
        )

    print()
    print("FIRST BAR:")
    print(bars[0])

    print()
    print("LAST BAR:")
    print(bars[-1])

    print()
    print("OHLCV VALUES:")
    print(
        "Open  :", bars[-1].open
    )
    print(
        "High  :", bars[-1].high
    )
    print(
        "Low   :", bars[-1].low
    )
    print(
        "Close :", bars[-1].close
    )
    print(
        "Volume:", bars[-1].volume
    )

    print()
    print("=" * 70)
    print("OHLCV REPOSITORY TEST PASSED")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())