import pandas as pd
import asyncio
import os

import yfinance as yf
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

# =========================
# 🔥 LOAD ENV
# =========================

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env")

# =========================
# 🔥 SYMBOLS
# =========================

SYMBOLS = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]

engine = create_async_engine(DATABASE_URL, echo=True)

# =========================
# ✅ INSERT / GET INSTRUMENT (FIXED)
# =========================

async def insert_instrument(conn, symbol: str):
    # Check if exists
    result = await conn.execute(
        text("SELECT id FROM instruments WHERE symbol = :symbol"),
        {"symbol": symbol},
    )
    row = result.fetchone()

    if row:
        return row[0]

    # ✅ FIXED INSERT (includes required fields)
    result = await conn.execute(
        text("""
        INSERT INTO instruments (
            symbol,
            name,
            exchange,
            asset_type,
            currency,
            is_active
        )
        VALUES (
            :symbol,
            :name,
            :exchange,
            :asset_type,
            :currency,
            :is_active
        )
        RETURNING id
        """),
        {
            "symbol": symbol,
            "name": symbol.split(".")[0],
            "exchange": "NSE",
            "asset_type": "equity",
            "currency": "INR",
            "is_active": True
        },
    )

    new_id = result.fetchone()[0]
    print(f"✅ Inserted instrument: {symbol}")
    return new_id


# =========================
# ✅ INSERT BARS
# =========================

async def insert_bars(conn, instrument_id, df):
    for _, row in df.iterrows():
        if pd.isna(row["Close"]):
            continue

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


# =========================
# ✅ INGEST SYMBOL
# =========================

async def ingest_symbol(symbol: str):
    print(f"\n📥 Fetching data for {symbol}...")

    df = yf.download(symbol, period="1y", interval="1d")

    # Fix MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.empty:
        print(f"❌ No data for {symbol}")
        return

    df = df.reset_index()

    async with engine.begin() as conn:
        instrument_id = await insert_instrument(conn, symbol)
        await insert_bars(conn, instrument_id, df)

    print(f"✅ Inserted OHLCV data for {symbol}")


# =========================
# ✅ MAIN
# =========================

async def main():
    for symbol in SYMBOLS:
        await ingest_symbol(symbol)


if __name__ == "__main__":
    asyncio.run(main())