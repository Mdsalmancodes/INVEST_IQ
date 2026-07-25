"""PredictionHistoryUseCase — backs the "Prediction History" API
endpoint. Thin read-side wrapper over
PredictionRunRepository.list_for_symbol(), per Document 4 §10.2 step 4's
description of this exact capability ("what powers the 'Predictions >
History' UI showing real historical accuracy").
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.ml.entities import PredictionRun
from src.domain.ml.repositories import PredictionRunRepository


@dataclass(frozen=True, slots=True)
class PredictionHistoryQuery:
    symbol: str
    limit: int = 20


class PredictionHistoryUseCase:
    def __init__(self, prediction_run_repository: PredictionRunRepository) -> None:
        self._prediction_run_repository = prediction_run_repository

    async def execute(self, query: PredictionHistoryQuery) -> tuple[PredictionRun, ...]:
        return await self._prediction_run_repository.list_for_symbol(
            query.symbol, limit=query.limit
        )
