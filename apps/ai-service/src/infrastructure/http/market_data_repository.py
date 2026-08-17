"""
INVEST IQ - MARKET DATA REPOSITORIES

This module contains two infrastructure implementations:

1. MarketDataRepository
   ---------------------
   Real Yahoo Finance repository.

   Used when the AI service itself needs to obtain real market data.

2. HttpMarketDataRepository
   ------------------------
   HTTP repository for obtaining market data from INVEST IQ core-api.

   Used by the AI-service architecture when market data is owned by
   core-api.

Both implementations return the same domain object:

    src.domain.ml.repositories.OhlcvBar

Important architecture rule
---------------------------

The AI/ML bounded context must not access the core-api database directly.

When using the HTTP implementation:

    AI Service
        |
        | HTTP
        v
    core-api
        |
        v
    PostgreSQL / market-data provider

No synthetic or fabricated market data is generated.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any, Tuple

import httpx
import pandas as pd
import yfinance as yf

from src.domain.ml.repositories import OhlcvBar


# ============================================================================
# EXCEPTIONS
# ============================================================================


class MarketDataUnavailableError(Exception):
    """
    Raised when real market data cannot be obtained or validated.
    """

    pass


# ============================================================================
# CONFIGURATION
# ============================================================================


DEFAULT_RETRIES = 3

DEFAULT_TIMEOUT_SECONDS = 20

MINIMUM_ROWS = 50

RETRY_DELAY_SECONDS = 2.0

REQUIRED_COLUMNS: tuple[str, ...] = (
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
)


# ============================================================================
# YAHOO FINANCE REPOSITORY
# ============================================================================


class MarketDataRepository:
    """
    Real Yahoo Finance market-data repository.

    This implementation downloads real market data directly from
    Yahoo Finance.

    Example
    -------

        repository = MarketDataRepository()

        bars = await repository.get_ohlcv_bars(
            "AAPL",
            date(2025, 1, 1),
            date(2026, 1, 1),
        )
    """

    async def get_ohlcv_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> Tuple[OhlcvBar, ...]:
        """
        Fetch real OHLCV bars from Yahoo Finance.
        """

        symbol = symbol.upper().strip()

        if not symbol:
            raise ValueError(
                "Market-data symbol must not be empty."
            )

        if not isinstance(start, date):
            raise TypeError(
                "start must be a datetime.date."
            )

        if not isinstance(end, date):
            raise TypeError(
                "end must be a datetime.date."
            )

        if start >= end:
            raise ValueError(
                "start date must be earlier than end date."
            )

        if not interval:
            raise ValueError(
                "interval must not be empty."
            )

        # --------------------------------------------------------------------
        # ENSURE SUFFICIENT HISTORY
        # --------------------------------------------------------------------

        requested_days = (
            end - start
        ).days

        if requested_days < 200:

            original_start = start

            start = (
                end
                - timedelta(days=365)
            )

            print(
                "Requested history was shorter than 200 "
                "calendar days."
            )

            print(
                f"Expanded start date from "
                f"{original_start} to {start}"
            )

        print(
            f"Fetching real Yahoo Finance data for "
            f"{symbol} from {start} to {end}"
        )

        dataframe: pd.DataFrame | None = None

        last_error: Exception | None = None

        # --------------------------------------------------------------------
        # RETRIES
        # --------------------------------------------------------------------

        for attempt in range(
            1,
            DEFAULT_RETRIES + 1,
        ):

            try:

                print(
                    f"Yahoo Finance attempt "
                    f"{attempt}/{DEFAULT_RETRIES}"
                )

                dataframe = await asyncio.to_thread(
                    self._download_from_yfinance,
                    symbol,
                    start,
                    end,
                    interval,
                )

                if dataframe is None:
                    raise MarketDataUnavailableError(
                        "Yahoo Finance returned no dataframe."
                    )

                if dataframe.empty:
                    raise MarketDataUnavailableError(
                        "Yahoo Finance returned an empty dataframe."
                    )

                print(
                    f"Yahoo Finance returned "
                    f"{len(dataframe)} rows."
                )

                break

            except Exception as exc:

                last_error = exc
                dataframe = None

                print(
                    f"Yahoo Finance attempt "
                    f"{attempt} failed: {exc}"
                )

                if attempt < DEFAULT_RETRIES:

                    print(
                        f"Retrying in "
                        f"{RETRY_DELAY_SECONDS:.1f} seconds..."
                    )

                    await asyncio.sleep(
                        RETRY_DELAY_SECONDS
                    )

        # --------------------------------------------------------------------
        # FAILURE
        # --------------------------------------------------------------------

        if dataframe is None:

            message = (
                f"Unable to retrieve real market data "
                f"for {symbol} after "
                f"{DEFAULT_RETRIES} attempts."
            )

            if last_error is not None:
                message += (
                    f" Last error: {last_error}"
                )

            raise MarketDataUnavailableError(
                message
            ) from last_error

        # --------------------------------------------------------------------
        # NORMALIZE
        # --------------------------------------------------------------------

        try:

            dataframe = self._normalize_data_frame(
                dataframe,
                symbol,
            )

        except Exception as exc:

            raise MarketDataUnavailableError(
                f"Yahoo Finance returned invalid market "
                f"data for {symbol}: {exc}"
            ) from exc

        # --------------------------------------------------------------------
        # DOMAIN CONVERSION
        # --------------------------------------------------------------------

        bars = self._convert_to_domain_bars(
            dataframe,
            symbol,
        )

        if not bars:

            raise MarketDataUnavailableError(
                f"No valid OHLCV bars could be created "
                f"for {symbol}."
            )

        print(
            f"Returning {len(bars)} real OHLCV bars."
        )

        return tuple(bars)

    # ========================================================================
    # YAHOO DOWNLOAD
    # ========================================================================

    @staticmethod
    def _download_from_yfinance(
        symbol: str,
        start: date,
        end: date,
        interval: str,
    ) -> pd.DataFrame:
        """
        Synchronous Yahoo Finance download.
        """

        dataframe = yf.download(
            symbol,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=False,
            progress=False,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            threads=False,
        )

        if dataframe is None:
            raise MarketDataUnavailableError(
                "yfinance returned None."
            )

        return dataframe

    # ========================================================================
    # YAHOO NORMALIZATION
    # ========================================================================

    @classmethod
    def _normalize_data_frame(
        cls,
        dataframe: pd.DataFrame,
        symbol: str,
    ) -> pd.DataFrame:
        """
        Normalize Yahoo Finance output.
        """

        df = dataframe.copy()

        if df.empty:
            raise ValueError(
                "Yahoo Finance dataframe is empty."
            )

        # --------------------------------------------------------------------
        # MULTIINDEX
        # --------------------------------------------------------------------

        if isinstance(
            df.columns,
            pd.MultiIndex,
        ):

            try:

                df.columns = (
                    df.columns.get_level_values(0)
                )

            except Exception as exc:

                raise ValueError(
                    "Unable to normalize Yahoo Finance "
                    "MultiIndex columns."
                ) from exc

        # --------------------------------------------------------------------
        # COLUMN NAMES
        # --------------------------------------------------------------------

        df.columns = [
            str(column).strip()
            for column in df.columns
        ]

        missing_columns = [
            column
            for column in REQUIRED_COLUMNS
            if column not in df.columns
        ]

        if missing_columns:

            raise ValueError(
                "Yahoo Finance response is missing "
                f"required columns: {missing_columns}"
            )

        # --------------------------------------------------------------------
        # ADJUSTED CLOSE
        # --------------------------------------------------------------------

        if "Adj Close" not in df.columns:

            df["Adj Close"] = df["Close"]

        # --------------------------------------------------------------------
        # SELECT COLUMNS
        # --------------------------------------------------------------------

        df = df[
            [
                "Open",
                "High",
                "Low",
                "Close",
                "Adj Close",
                "Volume",
            ]
        ].copy()

        # --------------------------------------------------------------------
        # DATETIME INDEX
        # --------------------------------------------------------------------

        if not isinstance(
            df.index,
            pd.DatetimeIndex,
        ):

            try:

                df.index = pd.to_datetime(
                    df.index,
                    errors="raise",
                )

            except Exception as exc:

                raise ValueError(
                    "Yahoo Finance index could not "
                    "be converted to DatetimeIndex."
                ) from exc

        # --------------------------------------------------------------------
        # TIMEZONE
        # --------------------------------------------------------------------

        if df.index.tz is not None:

            df.index = df.index.tz_convert(None)

        # --------------------------------------------------------------------
        # SORT
        # --------------------------------------------------------------------

        df = df.sort_index()

        # --------------------------------------------------------------------
        # DUPLICATES
        # --------------------------------------------------------------------

        if df.index.has_duplicates:

            df = df[
                ~df.index.duplicated(
                    keep="last"
                )
            ]

        # --------------------------------------------------------------------
        # NUMERIC
        # --------------------------------------------------------------------

        numeric_columns = [
            "Open",
            "High",
            "Low",
            "Close",
            "Adj Close",
            "Volume",
        ]

        for column in numeric_columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        # --------------------------------------------------------------------
        # MISSING
        # --------------------------------------------------------------------

        if df[numeric_columns].isna().any().any():

            invalid_columns = [
                column
                for column in numeric_columns
                if df[column].isna().any()
            ]

            raise ValueError(
                "Yahoo Finance data contains "
                "missing/non-numeric values in: "
                f"{invalid_columns}"
            )

        # --------------------------------------------------------------------
        # FINITE
        # --------------------------------------------------------------------

        values = df[
            numeric_columns
        ].to_numpy(
            dtype=float
        )

        if not pd.Series(
            values.flatten()
        ).apply(
            pd.notna
        ).all():

            raise ValueError(
                "Yahoo Finance data contains "
                "invalid numeric values."
            )

        # --------------------------------------------------------------------
        # POSITIVE PRICES
        # --------------------------------------------------------------------

        price_columns = [
            "Open",
            "High",
            "Low",
            "Close",
            "Adj Close",
        ]

        if (
            df[price_columns] <= 0
        ).any().any():

            raise ValueError(
                "Yahoo Finance returned "
                "non-positive price values."
            )

        # --------------------------------------------------------------------
        # HIGH
        # --------------------------------------------------------------------

        invalid_high = (
            df["High"]
            < df[
                [
                    "Open",
                    "Close",
                ]
            ].max(axis=1)
        )

        if invalid_high.any():

            raise ValueError(
                "Invalid OHLC data: High is below "
                "Open or Close."
            )

        # --------------------------------------------------------------------
        # LOW
        # --------------------------------------------------------------------

        invalid_low = (
            df["Low"]
            > df[
                [
                    "Open",
                    "Close",
                ]
            ].min(axis=1)
        )

        if invalid_low.any():

            raise ValueError(
                "Invalid OHLC data: Low is above "
                "Open or Close."
            )

        # --------------------------------------------------------------------
        # VOLUME
        # --------------------------------------------------------------------

        if (
            df["Volume"] < 0
        ).any():

            raise ValueError(
                "Yahoo Finance returned "
                "negative volume values."
            )

        # --------------------------------------------------------------------
        # MINIMUM ROWS
        # --------------------------------------------------------------------

        if len(df) < MINIMUM_ROWS:

            raise ValueError(
                f"Only {len(df)} valid market rows "
                f"were returned for {symbol}. "
                f"At least {MINIMUM_ROWS} rows are required."
            )

        return df

    # ========================================================================
    # DOMAIN CONVERSION
    # ========================================================================

    @staticmethod
    def _convert_to_domain_bars(
        dataframe: pd.DataFrame,
        symbol: str,
    ) -> list[OhlcvBar]:
        """
        Convert validated Yahoo Finance data to domain objects.
        """

        bars: list[OhlcvBar] = []

        for index, row in dataframe.iterrows():

            try:

                bar = OhlcvBar(
                    bar_time=index.to_pydatetime(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    adjusted_close=float(
                        row["Adj Close"]
                    ),
                    volume=int(row["Volume"]),
                )

            except Exception as exc:

                raise MarketDataUnavailableError(
                    f"Failed to convert validated Yahoo Finance "
                    f"row at {index} for {symbol} into OhlcvBar: "
                    f"{exc}"
                ) from exc

            bars.append(bar)

        if not bars:

            raise MarketDataUnavailableError(
                f"No valid OHLCV bars created for {symbol}."
            )

        return bars


# ============================================================================
# HTTP MARKET DATA REPOSITORY
# ============================================================================


class HttpMarketDataRepository:
    """
    HTTP implementation of the ML MarketDataRepository contract.

    The AI service obtains market data from core-api through HTTP.

    Example
    -------

        client = httpx.AsyncClient()

        repository = HttpMarketDataRepository(
            base_url="http://core-api:8001",
            client=client,
        )

        bars = await repository.get_ohlcv_bars(
            "AAPL",
            date(2024, 1, 1),
            date(2024, 1, 2),
        )

    The injected HTTP client is intentionally supported so unit tests can
    use httpx.MockTransport without requiring a live core-api instance.
    """

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient,
    ) -> None:

        if not isinstance(
            base_url,
            str,
        ):

            raise TypeError(
                "base_url must be a string."
            )

        base_url = base_url.strip()

        if not base_url:

            raise ValueError(
                "base_url must not be empty."
            )

        if not isinstance(
            client,
            httpx.AsyncClient,
        ):

            raise TypeError(
                "client must be an httpx.AsyncClient."
            )

        self._base_url = base_url.rstrip("/")

        self._client = client

    # ========================================================================
    # GET OHLCV BARS
    # ========================================================================

    async def get_ohlcv_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> tuple[OhlcvBar, ...]:
        """
        Retrieve OHLCV bars from core-api.
        """

        # --------------------------------------------------------------------
        # INPUT VALIDATION
        # --------------------------------------------------------------------

        if not isinstance(
            symbol,
            str,
        ):

            raise TypeError(
                "symbol must be a string."
            )

        symbol = symbol.strip().upper()

        if not symbol:

            raise ValueError(
                "symbol must not be empty."
            )

        if not isinstance(
            start,
            date,
        ):

            raise TypeError(
                "start must be a datetime.date."
            )

        if not isinstance(
            end,
            date,
        ):

            raise TypeError(
                "end must be a datetime.date."
            )

        if start >= end:

            raise ValueError(
                "start date must be earlier than end date."
            )

        if not isinstance(
            interval,
            str,
        ):

            raise TypeError(
                "interval must be a string."
            )

        interval = interval.strip()

        if not interval:

            raise ValueError(
                "interval must not be empty."
            )

        # --------------------------------------------------------------------
        # CORE-API ENDPOINT
        # --------------------------------------------------------------------

        url = (
            f"{self._base_url}"
            f"/api/v1/instruments/"
            f"{symbol}/bars"
        )

        params = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "interval": interval,
        }

        # --------------------------------------------------------------------
        # HTTP REQUEST
        # --------------------------------------------------------------------

        try:

            response = await self._client.get(
                url,
                params=params,
            )

            response.raise_for_status()

        except httpx.HTTPStatusError as exc:

            status_code = exc.response.status_code

            raise MarketDataUnavailableError(
                f"Failed to fetch market data for "
                f"{symbol}: core-api returned HTTP "
                f"{status_code}."
            ) from exc

        except httpx.HTTPError as exc:

            raise MarketDataUnavailableError(
                f"Failed to fetch market data for "
                f"{symbol}: {exc}"
            ) from exc

        except Exception as exc:

            raise MarketDataUnavailableError(
                f"Failed to fetch market data for "
                f"{symbol}: {exc}"
            ) from exc

        # --------------------------------------------------------------------
        # JSON RESPONSE
        # --------------------------------------------------------------------

        try:

            payload = response.json()

        except ValueError as exc:

            raise MarketDataUnavailableError(
                f"Failed to fetch market data for "
                f"{symbol}: core-api returned invalid JSON."
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):

            raise MarketDataUnavailableError(
                f"Failed to fetch market data for "
                f"{symbol}: core-api response must be "
                f"a JSON object."
            )

        # --------------------------------------------------------------------
        # VALIDATE SYMBOL WHEN PRESENT
        # --------------------------------------------------------------------

        response_symbol = payload.get(
            "symbol"
        )

        if response_symbol is not None:

            if (
                not isinstance(
                    response_symbol,
                    str,
                )
                or response_symbol.upper()
                != symbol
            ):

                raise MarketDataUnavailableError(
                    f"Failed to fetch market data for "
                    f"{symbol}: response symbol does not "
                    f"match requested symbol."
                )

        # --------------------------------------------------------------------
        # BARS
        # --------------------------------------------------------------------

        raw_bars = payload.get(
            "bars"
        )

        if raw_bars is None:

            raise MarketDataUnavailableError(
                f"Failed to fetch market data for "
                f"{symbol}: response does not contain "
                f"'bars'."
            )

        if not isinstance(
            raw_bars,
            list,
        ):

            raise MarketDataUnavailableError(
                f"Failed to fetch market data for "
                f"{symbol}: 'bars' must be a list."
            )

        # --------------------------------------------------------------------
        # CONVERT DOMAIN OBJECTS
        # --------------------------------------------------------------------

        bars: list[OhlcvBar] = []

        for index, raw_bar in enumerate(
            raw_bars
        ):

            if not isinstance(
                raw_bar,
                dict,
            ):

                raise MarketDataUnavailableError(
                    f"Failed to fetch market data for "
                    f"{symbol}: bar at index {index} "
                    f"must be an object."
                )

            try:

                bar = self._parse_bar(
                    raw_bar
                )

            except Exception as exc:

                raise MarketDataUnavailableError(
                    f"Failed to parse market data bar "
                    f"{index} for {symbol}: {exc}"
                ) from exc

            bars.append(bar)

        return tuple(bars)

    # ========================================================================
    # PARSE BAR
    # ========================================================================

    @staticmethod
    def _parse_bar(
        raw_bar: dict[str, Any],
    ) -> OhlcvBar:
        """
        Convert one core-api bar DTO into OhlcvBar.
        """

        required_fields = (
            "bar_time",
            "open",
            "high",
            "low",
            "close",
            "adjusted_close",
            "volume",
        )

        missing_fields = [
            field
            for field in required_fields
            if field not in raw_bar
        ]

        if missing_fields:

            raise ValueError(
                "Missing required fields: "
                f"{missing_fields}"
            )

        # --------------------------------------------------------------------
        # DATETIME
        # --------------------------------------------------------------------

        raw_bar_time = raw_bar[
            "bar_time"
        ]

        timestamp = pd.to_datetime(
            raw_bar_time,
            errors="raise",
            utc=True,
        )

        if pd.isna(timestamp):

            raise ValueError(
                "bar_time is invalid."
            )

        # --------------------------------------------------------------------
        # NUMERIC VALUES
        # --------------------------------------------------------------------

        open_price = float(
            raw_bar["open"]
        )

        high_price = float(
            raw_bar["high"]
        )

        low_price = float(
            raw_bar["low"]
        )

        close_price = float(
            raw_bar["close"]
        )

        adjusted_close = float(
            raw_bar["adjusted_close"]
        )

        volume = int(
            raw_bar["volume"]
        )

        # --------------------------------------------------------------------
        # FINITE VALUES
        # --------------------------------------------------------------------

        numeric_values = (
            open_price,
            high_price,
            low_price,
            close_price,
            adjusted_close,
        )

        if not all(
            pd.notna(value)
            for value in numeric_values
        ):

            raise ValueError(
                "OHLC price values must be finite."
            )

        # --------------------------------------------------------------------
        # POSITIVE PRICES
        # --------------------------------------------------------------------

        if any(
            value <= 0
            for value in numeric_values
        ):

            raise ValueError(
                "OHLC prices must be strictly positive."
            )

        # --------------------------------------------------------------------
        # OHLC RELATIONSHIPS
        # --------------------------------------------------------------------

        if high_price < max(
            open_price,
            close_price,
        ):

            raise ValueError(
                "high must be greater than or equal "
                "to open and close."
            )

        if low_price > min(
            open_price,
            close_price,
        ):

            raise ValueError(
                "low must be less than or equal "
                "to open and close."
            )

        # --------------------------------------------------------------------
        # VOLUME
        # --------------------------------------------------------------------

        if volume < 0:

            raise ValueError(
                "volume must not be negative."
            )

        # --------------------------------------------------------------------
        # DOMAIN OBJECT
        # --------------------------------------------------------------------

        return OhlcvBar(
            bar_time=timestamp.to_pydatetime(),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            adjusted_close=adjusted_close,
            volume=volume,
        )