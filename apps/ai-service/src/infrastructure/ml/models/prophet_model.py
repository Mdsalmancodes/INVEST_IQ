"""
Prophet price-forecasting model for INVEST IQ.

Role
----

Prophet is one of the three direct price-forecasting models:

    LSTM
    ARIMA
    Prophet

It is NOT a movement-classification model.

Its output is a sequence of future predicted prices which is later
converted by the DecisionEngine into:

    1-day forecast
    7-day forecast
    30-day forecast

Prophet is intended to capture:

    - long-term trend
    - recurring temporal patterns
    - seasonality
    - uncertainty intervals

The INVEST IQ architecture places Prophet alongside LSTM and ARIMA in
the price-forecasting layer, while Random Forest and XGBoost perform
up/down movement classification and FinBERT provides sentiment.
"""

from __future__ import annotations

import pickle
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from src.infrastructure.ml.models.metrics import RegressionMetrics


# ============================================================================
# CONFIGURATION
# ============================================================================

MINIMUM_HISTORY_DAYS = 30
"""
Minimum amount of historical observations required before Prophet training.

This is a model-level floor.

The DecisionEngine may additionally exclude Prophet when the supplied
history does not satisfy this requirement.
"""

DEFAULT_INTERVAL_WIDTH = 0.80

DEFAULT_DAILY_SEASONALITY = True

DEFAULT_WEEKLY_SEASONALITY = True

DEFAULT_YEARLY_SEASONALITY = False
"""
Yearly seasonality is disabled by default because stock-market histories
are represented as trading observations rather than a complete calendar
daily series.

It can be enabled later if the project's data frequency and validation
results justify it.
"""


# ============================================================================
# TRAIN RESULT
# ============================================================================


@dataclass(frozen=True, slots=True)
class ProphetTrainResult:
    """
    Result produced by Prophet training.
    """

    metrics: RegressionMetrics


# ============================================================================
# AVAILABILITY
# ============================================================================


@lru_cache(maxsize=1)
def is_available() -> bool:
    """
    Determine whether Prophet can be imported and instantiated.

    This function deliberately does NOT train a Prophet model.

    A real Prophet fit is performed later by train().

    Returns:
        True:
            Prophet package can be imported and instantiated.

        False:
            Prophet is unavailable.
    """

    try:
        from prophet import Prophet

        # Instantiation checks that the package itself is usable without
        # performing an expensive model fit.
        Prophet()

        return True

    except Exception:
        return False


# ============================================================================
# PROPHET MODEL
# ============================================================================


class ProphetModel:
    """
    Production-oriented wrapper around prophet.Prophet.

    Lifecycle:

        model = ProphetModel()

        model.train(
            dates,
            close_prices,
        )

        model.predict_next(
            steps_ahead=30,
        )

        model.save(path)

        loaded = ProphetModel.load(path)
    """

    def __init__(
        self,
        interval_width: float = DEFAULT_INTERVAL_WIDTH,
        daily_seasonality: bool = DEFAULT_DAILY_SEASONALITY,
        weekly_seasonality: bool = DEFAULT_WEEKLY_SEASONALITY,
        yearly_seasonality: bool = DEFAULT_YEARLY_SEASONALITY,
    ) -> None:

        if not 0.0 < interval_width < 1.0:
            raise ValueError(
                "interval_width must be between 0 and 1."
            )

        self._interval_width = float(
            interval_width
        )

        self._daily_seasonality = bool(
            daily_seasonality
        )

        self._weekly_seasonality = bool(
            weekly_seasonality
        )

        self._yearly_seasonality = bool(
            yearly_seasonality
        )

        self._fitted_model: Any | None = None

        self._last_date: pd.Timestamp | None = None

        self._feature_dates: tuple[str, ...] = ()

        self._is_fitted = False

    # ========================================================================
    # HISTORY CHECK
    # ========================================================================

    @staticmethod
    def has_sufficient_history(
        n_rows: int,
    ) -> bool:
        """
        Return whether the supplied history satisfies Prophet's minimum
        history requirement.
        """

        return (
            n_rows >= MINIMUM_HISTORY_DAYS
        )

    # ========================================================================
    # INPUT PREPARATION
    # ========================================================================

    @staticmethod
    def _prepare_dataframe(
        dates: npt.NDArray[np.datetime64] | list[Any],
        close_prices: npt.NDArray[np.float64] | list[float],
    ) -> pd.DataFrame:
        """
        Convert raw dates and prices into Prophet's required format:

            ds -> datetime
            y  -> numeric

        The method also:

            - removes invalid observations
            - sorts chronologically
            - removes duplicate dates
            - rejects non-positive/non-finite prices
        """

        if len(dates) != len(close_prices):
            raise ValueError(
                "dates and close_prices must "
                "contain the same number of observations."
            )

        if len(dates) == 0:
            raise ValueError(
                "Prophet cannot train on an empty dataset."
            )

        try:
            parsed_dates = pd.to_datetime(
                dates,
                errors="coerce",
                utc=True,
            )
        except Exception as exc:
            raise ValueError(
                "Prophet received invalid date data."
            ) from exc

        df = pd.DataFrame(
            {
                "ds": parsed_dates,
                "y": pd.to_numeric(
                    close_prices,
                    errors="coerce",
                ),
            }
        )

        # --------------------------------------------------------------------
        # REMOVE INVALID VALUES
        # --------------------------------------------------------------------

        df = df.dropna(
            subset=[
                "ds",
                "y",
            ]
        )

        if df.empty:
            raise ValueError(
                "Prophet received no valid date/price observations."
            )

        # --------------------------------------------------------------------
        # NORMALIZE TIMEZONE
        # --------------------------------------------------------------------

        # Prophet accepts timezone-naive timestamps most reliably.
        df["ds"] = (
            df["ds"]
            .dt.tz_convert(None)
        )

        # --------------------------------------------------------------------
        # SORT CHRONOLOGICALLY
        # --------------------------------------------------------------------

        df = (
            df.sort_values(
                "ds"
            )
            .reset_index(
                drop=True
            )
        )

        # --------------------------------------------------------------------
        # REMOVE DUPLICATE DATES
        # --------------------------------------------------------------------

        df = (
            df.drop_duplicates(
                subset=["ds"],
                keep="last",
            )
            .reset_index(
                drop=True
            )
        )

        # --------------------------------------------------------------------
        # NUMERIC VALIDATION
        # --------------------------------------------------------------------

        values = df["y"].to_numpy(
            dtype=float
        )

        if not np.isfinite(values).all():
            raise ValueError(
                "Prophet price data contains "
                "NaN or infinite values."
            )

        if (values <= 0).any():
            raise ValueError(
                "Prophet requires strictly positive "
                "stock prices."
            )

        if len(df) == 0:
            raise ValueError(
                "Prophet dataset became empty after cleaning."
            )

        return df

    # ========================================================================
    # TRAIN
    # ========================================================================

    def train(
        self,
        dates: npt.NDArray[np.datetime64],
        close_prices: npt.NDArray[np.float64],
    ) -> ProphetTrainResult:
        """
        Train Prophet using a chronological validation split.

        The validation model is fitted only on the historical training
        portion.

        After validation, a second Prophet model is fitted on the complete
        historical dataset for actual serving.
        """

        # --------------------------------------------------------------------
        # BASIC LENGTH CHECK
        # --------------------------------------------------------------------

        if len(close_prices) < MINIMUM_HISTORY_DAYS:
            raise ValueError(
                f"Prophet training requires at least "
                f"{MINIMUM_HISTORY_DAYS} rows, "
                f"got {len(close_prices)}."
            )

        # --------------------------------------------------------------------
        # AVAILABILITY
        # --------------------------------------------------------------------

        if not is_available():
            raise RuntimeError(
                "Prophet is unavailable in this environment. "
                "Ensure the Prophet package and its backend are correctly "
                "installed."
            )

        # --------------------------------------------------------------------
        # PREPARE DATA
        # --------------------------------------------------------------------

        df = self._prepare_dataframe(
            dates,
            close_prices,
        )

        if len(df) < MINIMUM_HISTORY_DAYS:
            raise ValueError(
                f"Prophet requires at least "
                f"{MINIMUM_HISTORY_DAYS} valid unique observations "
                f"after data cleaning; got {len(df)}."
            )

        # --------------------------------------------------------------------
        # CHRONOLOGICAL SPLIT
        # --------------------------------------------------------------------

        split_index = int(
            len(df) * 0.80
        )

        # For very small datasets, use the minimum history as the training
        # portion. This means a dataset of exactly 30 observations has no
        # separate holdout and is evaluated in-sample.
        split_index = max(
            MINIMUM_HISTORY_DAYS,
            split_index,
        )

        split_index = min(
            split_index,
            len(df),
        )

        train_df = df.iloc[
            :split_index
        ].copy()

        validation_df = df.iloc[
            split_index:
        ].copy()

        # --------------------------------------------------------------------
        # LOG TRAINING INFORMATION
        # --------------------------------------------------------------------

        print("=" * 78)
        print("PROPHET TRAINING")
        print(
            f"TOTAL ROWS       : {len(df)}"
        )
        print(
            f"TRAIN ROWS       : {len(train_df)}"
        )
        print(
            f"VALIDATION ROWS  : {len(validation_df)}"
        )
        print(
            f"TRAIN START      : {train_df['ds'].iloc[0]}"
        )
        print(
            f"TRAIN END        : {train_df['ds'].iloc[-1]}"
        )
        print("=" * 78)

        # --------------------------------------------------------------------
        # VALIDATION MODEL
        # --------------------------------------------------------------------

        validation_model = self._create_prophet()

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                validation_model.fit(
                    train_df
                )

        except Exception as exc:
            raise RuntimeError(
                "Prophet training failed while fitting "
                "the validation model."
            ) from exc

        # --------------------------------------------------------------------
        # VALIDATION
        # --------------------------------------------------------------------

        if len(validation_df) > 0:

            validation_days = len(
                validation_df
            )

            future = (
                validation_model
                .make_future_dataframe(
                    periods=validation_days,
                    freq="D",
                    include_history=True,
                )
            )

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                forecast = (
                    validation_model
                    .predict(future)
                )

            prediction_frame = (
                forecast[
                    [
                        "ds",
                        "yhat",
                    ]
                ]
                .copy()
            )

            prediction_frame["ds"] = (
                pd.to_datetime(
                    prediction_frame["ds"]
                )
                .dt.tz_localize(
                    None
                )
            )

            # ---------------------------------------------------------------
            # DATE ALIGNMENT
            # ---------------------------------------------------------------

            validation_predictions = (
                validation_df[
                    [
                        "ds",
                    ]
                ]
                .merge(
                    prediction_frame,
                    on="ds",
                    how="left",
                )
                .dropna(
                    subset=[
                        "yhat",
                    ]
                )
            )

            if len(validation_predictions) > 0:

                actual = (
                    validation_df[
                        validation_df["ds"].isin(
                            validation_predictions["ds"]
                        )
                    ]["y"]
                    .to_numpy(
                        dtype=float
                    )
                )

                predicted = (
                    validation_predictions[
                        "yhat"
                    ]
                    .to_numpy(
                        dtype=float
                    )
                )

                usable = min(
                    len(actual),
                    len(predicted),
                )

                if usable == 0:
                    raise RuntimeError(
                        "Prophet produced no usable validation predictions."
                    )

                metrics = RegressionMetrics.compute(
                    actual[:usable],
                    predicted[:usable],
                )

            else:

                # Calendar-day forecasting can fail to align with a dataset
                # containing only trading days. Use the final forecast values
                # as a deterministic fallback.
                forecast_tail = (
                    forecast[
                        "yhat"
                    ]
                    .to_numpy(
                        dtype=float
                    )[
                        -len(validation_df):
                    ]
                )

                actual = (
                    validation_df[
                        "y"
                    ]
                    .to_numpy(
                        dtype=float
                    )
                )

                usable = min(
                    len(actual),
                    len(forecast_tail),
                )

                if usable == 0:
                    raise RuntimeError(
                        "Prophet produced no usable validation predictions."
                    )

                metrics = RegressionMetrics.compute(
                    actual[-usable:],
                    forecast_tail[-usable:],
                )

        else:

            # ----------------------------------------------------------------
            # NO HOLDOUT
            # ----------------------------------------------------------------
            #
            # This occurs when the dataset is exactly at the minimum history.
            # Evaluate the fitted validation model in-sample rather than
            # fabricating a validation period.
            # ----------------------------------------------------------------

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                in_sample_forecast = (
                    validation_model.predict(
                        train_df
                    )
                )

            metrics = RegressionMetrics.compute(
                train_df[
                    "y"
                ].to_numpy(
                    dtype=float
                ),
                in_sample_forecast[
                    "yhat"
                ].to_numpy(
                    dtype=float
                ),
            )

        # --------------------------------------------------------------------
        # FINAL FULL-HISTORY MODEL
        # --------------------------------------------------------------------

        full_model = self._create_prophet()

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                full_model.fit(
                    df
                )

        except Exception as exc:
            raise RuntimeError(
                "Prophet training failed while fitting "
                "the final full-history model."
            ) from exc

        # --------------------------------------------------------------------
        # SAVE IN MEMORY
        # --------------------------------------------------------------------

        self._fitted_model = full_model

        self._last_date = pd.Timestamp(
            df["ds"].iloc[-1]
        )

        self._feature_dates = tuple(
            timestamp.isoformat()
            for timestamp in df["ds"]
        )

        self._is_fitted = True

        # --------------------------------------------------------------------
        # LOG RESULTS
        # --------------------------------------------------------------------

        print("=" * 78)
        print("PROPHET TRAINING COMPLETE")
        print(
            f"METRICS          : {metrics.as_dict()}"
        )
        print(
            f"LAST DATE        : {self._last_date}"
        )
        print("=" * 78)

        return ProphetTrainResult(
            metrics=metrics
        )

    # ========================================================================
    # MODEL FACTORY
    # ========================================================================

    def _create_prophet(self) -> Any:
        """
        Construct the Prophet estimator using this instance's configuration.
        """

        try:
            from prophet import Prophet

        except Exception as exc:
            raise RuntimeError(
                "The Prophet package could not be imported."
            ) from exc

        return Prophet(
            interval_width=self._interval_width,
            daily_seasonality=self._daily_seasonality,
            weekly_seasonality=self._weekly_seasonality,
            yearly_seasonality=self._yearly_seasonality,
            uncertainty_samples=1000,
        )

    # ========================================================================
    # INFERENCE
    # ========================================================================

    def predict_next(
        self,
        steps_ahead: int = 1,
    ) -> list[float]:
        """
        Predict future prices.

        Args:
            steps_ahead:
                Number of future calendar periods to forecast.

        Returns:
            List of predicted prices.
        """

        if not self._is_fitted:
            raise RuntimeError(
                "train() must be called before predict_next()."
            )

        if self._fitted_model is None:
            raise RuntimeError(
                "Prophet fitted model is unavailable."
            )

        if not isinstance(
            steps_ahead,
            int,
        ):
            raise TypeError(
                "steps_ahead must be an integer."
            )

        if steps_ahead <= 0:
            raise ValueError(
                "steps_ahead must be greater than zero."
            )

        future = (
            self._fitted_model
            .make_future_dataframe(
                periods=steps_ahead,
                freq="D",
                include_history=True,
            )
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            forecast = (
                self._fitted_model
                .predict(future)
            )

        predictions = (
            forecast[
                "yhat"
            ]
            .to_numpy(
                dtype=float
            )[
                -steps_ahead:
            ]
        )

        if len(predictions) != steps_ahead:
            raise RuntimeError(
                "Prophet returned an unexpected "
                "number of predictions."
            )

        if not np.isfinite(
            predictions
        ).all():
            raise RuntimeError(
                "Prophet returned NaN or infinite predictions."
            )

        # Stock prices cannot be negative.
        predictions = np.maximum(
            predictions,
            0.0,
        )

        return [
            float(value)
            for value in predictions
        ]

    # ========================================================================
    # PREDICT WITH INTERVALS
    # ========================================================================

    def predict_next_with_intervals(
        self,
        steps_ahead: int = 1,
    ) -> list[
        tuple[float, float, float]
    ]:
        """
        Return:

            (predicted_price, lower_bound, upper_bound)

        for every future period.

        This is useful for the Forecast domain entity's uncertainty bands.
        """

        if not self._is_fitted:
            raise RuntimeError(
                "train() must be called before prediction."
            )

        if self._fitted_model is None:
            raise RuntimeError(
                "Prophet fitted model is unavailable."
            )

        if not isinstance(
            steps_ahead,
            int,
        ):
            raise TypeError(
                "steps_ahead must be an integer."
            )

        if steps_ahead <= 0:
            raise ValueError(
                "steps_ahead must be greater than zero."
            )

        future = (
            self._fitted_model
            .make_future_dataframe(
                periods=steps_ahead,
                freq="D",
                include_history=True,
            )
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            forecast = (
                self._fitted_model
                .predict(future)
            )

        tail = (
            forecast[
                [
                    "yhat",
                    "yhat_lower",
                    "yhat_upper",
                ]
            ]
            .tail(
                steps_ahead
            )
        )

        results: list[
            tuple[float, float, float]
        ] = []

        for row in tail.itertuples(
            index=False
        ):

            predicted = float(
                row.yhat
            )

            lower = float(
                row.yhat_lower
            )

            upper = float(
                row.yhat_upper
            )

            if not all(
                math_is_finite(value)
                for value in (
                    predicted,
                    lower,
                    upper,
                )
            ):
                raise RuntimeError(
                    "Prophet produced invalid "
                    "forecast interval values."
                )

            lower = max(
                0.0,
                lower,
            )

            upper = max(
                lower,
                upper,
            )

            results.append(
                (
                    predicted,
                    lower,
                    upper,
                )
            )

        if len(results) != steps_ahead:
            raise RuntimeError(
                "Prophet returned an unexpected "
                "number of forecast intervals."
            )

        return results

    # ========================================================================
    # SAVE
    # ========================================================================

    def save(
        self,
        path: str | Path,
    ) -> None:
        """
        Persist the fitted Prophet model and metadata.
        """

        if not self._is_fitted:
            raise RuntimeError(
                "train() must be called before save()."
            )

        if self._fitted_model is None:
            raise RuntimeError(
                "Cannot save an empty Prophet model."
            )

        artifact_path = Path(
            path
        )

        artifact_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "artifact_type": (
                "invest-iq-prophet-model"
            ),
            "artifact_version": 1,
            "fitted_model": (
                self._fitted_model
            ),
            "last_date": (
                self._last_date
            ),
            "feature_dates": (
                self._feature_dates
            ),
            "interval_width": (
                self._interval_width
            ),
            "daily_seasonality": (
                self._daily_seasonality
            ),
            "weekly_seasonality": (
                self._weekly_seasonality
            ),
            "yearly_seasonality": (
                self._yearly_seasonality
            ),
        }

        with artifact_path.open(
            "wb"
        ) as file:

            pickle.dump(
                payload,
                file,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

    # ========================================================================
    # LOAD
    # ========================================================================

    @classmethod
    def load(
        cls,
        path: str | Path,
    ) -> ProphetModel:
        """
        Load a previously trained Prophet artifact.
        """

        artifact_path = Path(
            path
        )

        if not artifact_path.exists():
            raise FileNotFoundError(
                f"Prophet artifact not found: "
                f"{artifact_path}"
            )

        if not artifact_path.is_file():
            raise ValueError(
                f"Prophet artifact path is not a file: "
                f"{artifact_path}"
            )

        with artifact_path.open(
            "rb"
        ) as file:

            payload = pickle.load(
                file
            )

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "Invalid Prophet artifact format."
            )

        if payload.get(
            "artifact_type"
        ) != "invest-iq-prophet-model":
            raise ValueError(
                "Artifact is not a valid INVEST IQ Prophet model."
            )

        required_keys = {
            "fitted_model",
            "last_date",
        }

        missing_keys = (
            required_keys
            - set(payload.keys())
        )

        if missing_keys:
            raise ValueError(
                "Prophet artifact is missing "
                f"required fields: "
                f"{sorted(missing_keys)}"
            )

        fitted_model = payload.get(
            "fitted_model"
        )

        if fitted_model is None:
            raise ValueError(
                "Prophet artifact contains no fitted model."
            )

        instance = cls(
            interval_width=float(
                payload.get(
                    "interval_width",
                    DEFAULT_INTERVAL_WIDTH,
                )
            ),
            daily_seasonality=bool(
                payload.get(
                    "daily_seasonality",
                    DEFAULT_DAILY_SEASONALITY,
                )
            ),
            weekly_seasonality=bool(
                payload.get(
                    "weekly_seasonality",
                    DEFAULT_WEEKLY_SEASONALITY,
                )
            ),
            yearly_seasonality=bool(
                payload.get(
                    "yearly_seasonality",
                    DEFAULT_YEARLY_SEASONALITY,
                )
            ),
        )

        instance._fitted_model = (
            fitted_model
        )

        last_date = payload.get(
            "last_date"
        )

        if last_date is not None:
            instance._last_date = pd.Timestamp(
                last_date
            )

        instance._feature_dates = tuple(
            payload.get(
                "feature_dates",
                (),
            )
        )

        instance._is_fitted = True

        return instance


# ============================================================================
# NUMERIC HELPER
# ============================================================================


def math_is_finite(
    value: float,
) -> bool:
    """
    Small local finite-number helper.
    """

    return bool(
        np.isfinite(
            float(value)
        )
    )