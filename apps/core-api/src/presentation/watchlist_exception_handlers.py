"""Centralized exception handling for the watchlist bounded context —
mirrors src.presentation.portfolio_exception_handlers's pattern.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from src.domain.watchlist.exceptions import (
    DefaultWatchlistAlreadyExistsError,
    DuplicateWatchlistItemError,
    InvalidWatchlistNameError,
    WatchlistDomainError,
    WatchlistItemNotFoundError,
    WatchlistNotFoundError,
    WatchlistOwnershipError,
)

_EXCEPTION_STATUS_MAP: dict[type[WatchlistDomainError], int] = {
    WatchlistNotFoundError: status.HTTP_404_NOT_FOUND,
    WatchlistItemNotFoundError: status.HTTP_404_NOT_FOUND,
    WatchlistOwnershipError: status.HTTP_403_FORBIDDEN,
    DuplicateWatchlistItemError: status.HTTP_409_CONFLICT,
    InvalidWatchlistNameError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    DefaultWatchlistAlreadyExistsError: status.HTTP_409_CONFLICT,
}


def raise_watchlist_exception_as_http(exc: WatchlistDomainError) -> None:
    status_code = _EXCEPTION_STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc
