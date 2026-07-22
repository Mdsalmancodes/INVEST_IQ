"""Shared instrument-resolution helper for market_data use cases — avoids
duplicating the same "look up by symbol, raise if missing" pattern across
5 use cases, mirroring src.application.portfolio.ownership's role for
the portfolio context.
"""

from __future__ import annotations

from src.domain.market_data.entities import Instrument
from src.domain.market_data.exceptions import InstrumentNotFoundError
from src.domain.market_data.repositories import InstrumentRepository


async def get_instrument_by_symbol_or_raise(
    instrument_repository: InstrumentRepository, symbol: str
) -> Instrument:
    instrument = await instrument_repository.get_by_symbol(symbol)
    if instrument is None:
        raise InstrumentNotFoundError(f"No instrument found for symbol {symbol!r}")
    return instrument
