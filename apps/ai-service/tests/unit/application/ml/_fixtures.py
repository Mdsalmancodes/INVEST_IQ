"""Shared test fixtures for AI/ML application-layer use case tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np

from src.domain.ml.entities import PredictionRun
from src.domain.ml.repositories import OhlcvBar
from src.domain.ml.value_objects import PredictionRunId


def synthetic_bars(n: int = 100, seed: int = 41, trend: float = 0.05) -> tuple[OhlcvBar, ...]:
    """Real, ascending-date synthetic OHLCV bars — ascending dates matter
    (not just realistic-looking data): Prophet's internal optimizer
    rejects a constant/degenerate `ds` column, so every bar must have a
    genuinely distinct, increasing bar_time."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=trend, scale=1.0, size=n)
    closes = 100 + np.cumsum(steps)
    dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    return tuple(
        OhlcvBar(
            bar_time=bar_date,
            open=float(c) - 0.5,
            high=float(c) + 1.0,
            low=float(c) - 1.0,
            close=float(c),
            adjusted_close=float(c),
            volume=500_000,
        )
        for bar_date, c in zip(dates, closes, strict=True)
    )


class FakeMarketDataRepository:
    def __init__(self, bars_by_symbol: dict[str, tuple[OhlcvBar, ...]] | None = None) -> None:
        self._bars_by_symbol = bars_by_symbol or {}
        self._default_bars: tuple[OhlcvBar, ...] = ()

    @classmethod
    def with_default_bars(cls, bars: tuple[OhlcvBar, ...]) -> FakeMarketDataRepository:
        instance = cls()
        instance._default_bars = bars
        return instance

    async def get_ohlcv_bars(
        self, symbol: str, start: date, end: date, interval: str = "1d"
    ) -> tuple[OhlcvBar, ...]:
        return self._bars_by_symbol.get(symbol.upper(), self._default_bars)


class FakePredictionRunRepository:
    def __init__(self) -> None:
        self.saved: list[PredictionRun] = []

    async def save(self, prediction_run: PredictionRun) -> None:
        self.saved.append(prediction_run)

    async def get_by_id(self, prediction_run_id: PredictionRunId) -> PredictionRun | None:
        return next((r for r in self.saved if r.id == prediction_run_id), None)

    async def list_for_symbol(self, symbol: str, limit: int = 20) -> tuple[PredictionRun, ...]:
        matching = tuple(r for r in self.saved if r.symbol == symbol.upper())
        return tuple(reversed(matching))[:limit]
