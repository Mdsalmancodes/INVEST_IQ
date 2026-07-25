"""Centralized exception handling for the AI/ML bounded context — mirrors
core-api's presentation/*_exception_handlers.py pattern.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from src.domain.ml.exceptions import (
    InsufficientDataError,
    InvalidForecastHorizonError,
    MlDomainError,
    ModelUnavailableError,
    ModelVersionNotFoundError,
    PredictionRunNotFoundError,
)
from src.infrastructure.http.market_data_repository import MarketDataUnavailableError

_EXCEPTION_STATUS_MAP: dict[type[MlDomainError], int] = {
    InsufficientDataError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ModelUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    MarketDataUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    PredictionRunNotFoundError: status.HTTP_404_NOT_FOUND,
    ModelVersionNotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidForecastHorizonError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def raise_ml_exception_as_http(exc: MlDomainError) -> None:
    status_code = _EXCEPTION_STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc
