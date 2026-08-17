"""
Repository interfaces (Protocols) for the AI/ML bounded context.

INVEST IQ
=========

The domain layer defines repository contracts.

Infrastructure implements these contracts.

Dependency direction:

    API
      ↓
    Application
      ↓
    Domain contracts
      ↑
    Infrastructure

The AI service never opens the core-api PostgreSQL database directly.

Market data is obtained through the existing core-api HTTP endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from src.domain.ml.entities import (
    ModelVersion,
    PredictionRun,
)

from src.domain.ml.value_objects import (
    ModelFamily,
    ModelVersionId,
    PredictionRunId,
)


# ============================================================================
# OHLCV
# ============================================================================


@dataclass(frozen=True, slots=True)
class OhlcvBar:
    """
    Canonical OHLCV bar used inside the AI/ML bounded context.

    This is deliberately independent of the core-api DTO.

    Infrastructure is responsible for mapping external market-data
    responses into this domain object.
    """

    bar_time: datetime
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


# ============================================================================
# MARKET DATA REPOSITORY
# ============================================================================


class MarketDataRepository(Protocol):
    """
    Repository contract for historical market data.

    The concrete implementation lives in infrastructure.

    INVEST IQ reuses the existing core-api market-data module rather than
    duplicating the OHLCV database inside ai-service.
    """

    async def get_ohlcv_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> tuple[OhlcvBar, ...]:
        """
        Return canonical OHLCV bars for the requested symbol/date range.
        """

        ...


# ============================================================================
# MODEL REGISTRY REPOSITORY
# ============================================================================


class ModelRegistryRepository(Protocol):
    """
    Repository contract for trained model-version metadata.

    IMPORTANT
    ---------

    ModelVersion is SYMBOL-AWARE.

    Therefore a trained model is selected using:

        model family + stock symbol

    Example:

        lstm + AAPL
        lstm + TSLA

    must never be treated as the same active model.
    """

    async def save(
        self,
        model_version: ModelVersion,
    ) -> None:
        """
        Persist a ModelVersion.
        """

        ...

    async def get_by_id(
        self,
        model_version_id: ModelVersionId,
    ) -> ModelVersion | None:
        """
        Retrieve one model version by ID.
        """

        ...

    async def get_active_for_family_and_symbol(
        self,
        family: ModelFamily,
        symbol: str,
    ) -> ModelVersion | None:
        """
        Return the newest active model version for:

            family + symbol

        Example:

            get_active_for_family_and_symbol(
                "lstm",
                "AAPL",
            )

        must return an AAPL LSTM model only.

        It must never return a model trained for another symbol.
        """

        ...

    async def list_for_family(
        self,
        family: ModelFamily,
    ) -> tuple[ModelVersion, ...]:
        """
        List all registered versions for a model family.
        """

        ...

    async def delete(
        self,
        model_version_id: ModelVersionId,
    ) -> bool:
        """
        Delete the registry record for a model version.

        Returns:

            True  -> record existed and was deleted
            False -> record did not exist
        """

        ...


# ============================================================================
# PREDICTION RUN REPOSITORY
# ============================================================================


class PredictionRunRepository(Protocol):
    """
    Repository contract for immutable completed prediction runs.
    """

    async def save(
        self,
        prediction_run: PredictionRun,
    ) -> None:
        """
        Persist a completed PredictionRun.
        """

        ...

    async def get_by_id(
        self,
        prediction_run_id: PredictionRunId,
    ) -> PredictionRun | None:
        """
        Retrieve a PredictionRun by ID.
        """

        ...

    async def list_for_symbol(
        self,
        symbol: str,
        limit: int = 20,
    ) -> tuple[PredictionRun, ...]:
        """
        Return recent prediction runs for a symbol.
        """

        ...