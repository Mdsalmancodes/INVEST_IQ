"""CreateAlertUseCase, DeleteAlertUseCase.

CreateAlertUseCase accepts a `symbol` string (not a raw instrument_id) and
resolves it via market_data's InstrumentRepository — matching
AddWatchlistItemUseCase's convention that any user-facing, symbol-keyed
input resolves through get_instrument_by_symbol_or_raise before touching
the alerts repository. This is Phase 6's integration point with Phase 4's
Market Data Foundation, exactly as Phase 5's Watchlist context established.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.application.alerts.ownership import get_owned_alert_or_raise
from src.application.market_data.instrument_resolution import get_instrument_by_symbol_or_raise
from src.domain.alerts.entities import Alert, ConditionType
from src.domain.alerts.exceptions import DuplicateAlertError
from src.domain.alerts.repositories import AlertRepository
from src.domain.alerts.value_objects import AlertId
from src.domain.market_data.repositories import InstrumentRepository


@dataclass(frozen=True, slots=True)
class CreateAlertCommand:
    user_id: str
    symbol: str
    condition_type: ConditionType
    threshold: Decimal
    is_recurring: bool = False
    cooldown_minutes: int = 0


class CreateAlertUseCase:
    def __init__(
        self,
        alert_repository: AlertRepository,
        instrument_repository: InstrumentRepository,
    ) -> None:
        self._alert_repository = alert_repository
        self._instrument_repository = instrument_repository

    async def execute(self, command: CreateAlertCommand) -> Alert:
        instrument = await get_instrument_by_symbol_or_raise(
            self._instrument_repository, command.symbol
        )

        # Application-layer defense-in-depth companion to the DB's
        # uq_alerts_duplicate UNIQUE constraint (user_id, instrument_id,
        # condition_type, threshold) — matches CreateWatchlistUseCase's
        # pre-check pattern for the default-watchlist invariant.
        is_duplicate = await self._alert_repository.exists_duplicate(
            user_id=command.user_id,
            instrument_id=instrument.id,
            condition_type=command.condition_type,
            threshold=command.threshold,
        )
        if is_duplicate:
            raise DuplicateAlertError(
                f"An alert for {command.symbol!r} with condition "
                f"{command.condition_type!r} at threshold {command.threshold} already exists"
            )

        alert = Alert.create(
            user_id=command.user_id,
            instrument_id=instrument.id,
            condition_type=command.condition_type,
            threshold=command.threshold,
            is_recurring=command.is_recurring,
            cooldown_minutes=command.cooldown_minutes,
        )
        await self._alert_repository.save(alert)
        return alert


class DeleteAlertUseCase:
    def __init__(self, alert_repository: AlertRepository) -> None:
        self._alert_repository = alert_repository

    async def execute(self, alert_id: AlertId, requesting_user_id: str) -> None:
        await get_owned_alert_or_raise(self._alert_repository, alert_id, requesting_user_id)
        await self._alert_repository.delete(alert_id)
