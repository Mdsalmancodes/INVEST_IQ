"""GetCorporateActionsUseCase — surfaces splits/dividends/spinoffs backing
adjusted_close, per Document 4's endpoint catalog note: "NEW — surfaces
splits/dividends backing adjusted_close."
"""

from __future__ import annotations

from src.application.market_data.instrument_resolution import get_instrument_by_symbol_or_raise
from src.domain.market_data.entities import CorporateAction
from src.domain.market_data.repositories import CorporateActionRepository, InstrumentRepository


class GetCorporateActionsUseCase:
    def __init__(
        self,
        instrument_repository: InstrumentRepository,
        corporate_action_repository: CorporateActionRepository,
    ) -> None:
        self._instrument_repository = instrument_repository
        self._corporate_action_repository = corporate_action_repository

    async def execute(self, symbol: str) -> tuple[CorporateAction, ...]:
        instrument = await get_instrument_by_symbol_or_raise(self._instrument_repository, symbol)
        return await self._corporate_action_repository.list_for_instrument(instrument.id)
