import asyncio
import uuid

from dotenv import load_dotenv

load_dotenv()

from src.infrastructure.persistence.postgres.session import (
    get_session_factory,
)
from src.infrastructure.persistence.postgres.portfolio_models import (
    InstrumentModel,
)


async def seed() -> None:
    session_factory = get_session_factory()

    instruments = [
        InstrumentModel(
            id=uuid.uuid4(),
            symbol="AAPL",
            exchange="NASDAQ",
            name="Apple Inc.",
            asset_type="equity",
            currency="USD",
            is_active=True,
        ),
        InstrumentModel(
            id=uuid.uuid4(),
            symbol="RELIANCE.NS",
            exchange="NSE",
            name="Reliance Industries",
            asset_type="equity",
            currency="INR",
            is_active=True,
        ),
        InstrumentModel(
            id=uuid.uuid4(),
            symbol="TCS.NS",
            exchange="NSE",
            name="Tata Consultancy Services",
            asset_type="equity",
            currency="INR",
            is_active=True,
        ),
        InstrumentModel(
            id=uuid.uuid4(),
            symbol="INFY.NS",
            exchange="NSE",
            name="Infosys",
            asset_type="equity",
            currency="INR",
            is_active=True,
        ),
    ]

    async with session_factory() as session:
        for instrument in instruments:
            existing = await session.get(
                InstrumentModel,
                instrument.id,
            )

            # Avoid inserting duplicates by symbol + exchange.
            from sqlalchemy import select

            result = await session.execute(
                select(InstrumentModel).where(
                    InstrumentModel.symbol == instrument.symbol,
                    InstrumentModel.exchange == instrument.exchange,
                )
            )

            existing_by_symbol = result.scalar_one_or_none()

            if existing_by_symbol:
                print(
                    f"⏭️ Already exists: "
                    f"{instrument.symbol}"
                )
                continue

            session.add(instrument)

            print(
                f"✅ Added: "
                f"{instrument.symbol} "
                f"({instrument.exchange})"
            )

        await session.commit()

    print("✅ INSTRUMENT SEED COMPLETED")


if __name__ == "__main__":
    asyncio.run(seed())