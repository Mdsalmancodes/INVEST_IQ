import asyncio
import uuid
from dotenv import load_dotenv

load_dotenv()

from src.infrastructure.persistence.postgres.session import get_session_factory
from src.infrastructure.persistence.postgres.models import InstrumentModel


async def seed():
    session_factory = get_session_factory()

    async with session_factory() as session:
        instruments = [
            InstrumentModel(
                id=uuid.uuid4(),
                symbol="AAPL",
                exchange="NASDAQ",
                name="Apple Inc",
                asset_type="equity",
                currency="USD",
                is_active=True,
            ),
            InstrumentModel(
                id=uuid.uuid4(),
                symbol="TSLA",
                exchange="NASDAQ",
                name="Tesla Inc",
                asset_type="equity",
                currency="USD",
                is_active=True,
            ),
            InstrumentModel(
                id=uuid.uuid4(),
                symbol="GOOGL",
                exchange="NASDAQ",
                name="Alphabet Inc",
                asset_type="equity",
                currency="USD",
                is_active=True,
            ),
            InstrumentModel(
                id=uuid.uuid4(),
                symbol="MSFT",
                exchange="NASDAQ",
                name="Microsoft",
                asset_type="equity",
                currency="USD",
                is_active=True,
            ),
        ]

        session.add_all(instruments)
        await session.commit()

        print("✅ SEEDED SUCCESSFULLY")


if __name__ == "__main__":
    asyncio.run(seed())