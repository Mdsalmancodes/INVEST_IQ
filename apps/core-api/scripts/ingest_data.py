import pandas as pd
import asyncio

import yfinance as yf
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# 🔥 DB CONNECTION
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/investiq"

# 🔥 SYMBOLS
SYMBOLS = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]

engine = create_async_engine(DATABASE_URL, echo=True)


# ✅ STEP 1 — GET instrument_id
async def get_instrument_id(conn, symbol: str):
    result = await conn.execute(
        text("SELECT id FROM instruments WHERE symbol = :symbol"),
        {"symbol": symbol},
    )
    row = result.fetchone()
    return row[0] if row else None


# ✅ STEP 2 — INSERT BARS
async def insert_bars(conn, instrument_id, df):
    for _, row in df.iterrows():
        await conn.execute(
            text("""
                INSERT INTO ohlcv_bars (
                    instrument_id,
                    interval,
                    source,
                    bar_time,
                    open,
                    high,
                    low,
                    close,
                    adjusted_close,
                    volume
                )
                VALUES (
                    :instrument_id,
                    :interval,
                    :source,
                    :bar_time,
                    :open,
                    :high,
                    :low,
                    :close,
                    :adj_close,
                    :volume
                )
                ON CONFLICT DO NOTHING
            """),
            {
                "instrument_id": instrument_id,
                "interval": "1d",
                "source": "yahoo",
                "bar_time": row["Date"].to_pydatetime(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "adj_close": float(row.get("Adj Close", row["Close"])),
                "volume": int(row["Volume"]),
            },
        )


# ✅ STEP 3 — INGEST ONE SYMBOL
async def ingest_symbol(symbol: str):
    print(f"\n📥 Fetching data for {symbol}...")

    df = yf.download(symbol, period="1y", interval="1d", group_by="column")

    # Fix MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.empty:
        print(f"❌ No data for {symbol}")
        return

    # 🔥 IMPORTANT FIX
    df = df.reset_index()

    async with engine.begin() as conn:
        instrument_id = await get_instrument_id(conn, symbol)

        if not instrument_id:
            print(f"❌ Instrument not found: {symbol}")
            return

        await insert_bars(conn, instrument_id, df)

    print(f"✅ Inserted OHLCV data for {symbol}")


# ✅ STEP 4 — MAIN
async def main():
    for symbol in SYMBOLS:
        await ingest_symbol(symbol)


if __name__ == "__main__":
    asyncio.run(main())