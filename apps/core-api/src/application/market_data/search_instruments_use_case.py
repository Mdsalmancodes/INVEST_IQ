"""SearchInstrumentsUseCase — backs the StockSearch frontend component
(founder's explicit Phase 4 frontend requirement). Per Document 4's
already-frozen catalog entry `GET /api/v1/instruments/search?q=` — this
endpoint was named in the frozen architecture but not part of the
original 5-API backend list the founder enumerated; built now because
StockSearch cannot function without it (a search box with no search
endpoint is not a real implementation of the requested component).
"""

from __future__ import annotations

from src.domain.market_data.entities import Instrument
from src.domain.market_data.repositories import InstrumentRepository


class SearchInstrumentsUseCase:
    def __init__(self, instrument_repository: InstrumentRepository) -> None:
        self._instrument_repository = instrument_repository

    async def execute(self, query: str, limit: int = 20) -> tuple[Instrument, ...]:
        return await self._instrument_repository.search(query, limit)
