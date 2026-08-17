"""
ARIMA price-forecasting model for INVEST IQ.

Model
-----
statsmodels.tsa.arima.model.ARIMA

Purpose
-------
Provide a classical statistical time-series forecasting baseline for
short-horizon price forecasting.

ARIMA is used alongside:

    - LSTM
    - Prophet
    - Random Forest
    - XGBoost
    - FinBERT

Responsibilities
----------------
    - Train an ARIMA model on historical closing prices.
    - Perform chronological train/validation evaluation.
    - Refit the model on the complete training history.
    - Produce multi-step forecasts.
    - Persist the fitted model artifact.
    - Load a previously trained artifact for inference.

Important architecture rule
---------------------------
Training is performed by TrainModelUseCase.

DecisionEngine performs inference only.

The model loaded by ModelLoader is already fitted. ARIMA is therefore
NOT refitted inside DecisionEngine.

Architecture:

    MarketDataRepository
            ↓
    TrainModelUseCase
            ↓
       ArimaModel.train()
            ↓
       ArimaModel.save()
            ↓
      Model Registry
            ↓
       ModelLoader
            ↓
       ArimaModel.load()
            ↓
       DecisionEngine
            ↓
       ArimaModel.predict_next()

The fitted ARIMA result is persisted as a trusted local artifact.
"""

from __future__ import annotations

import pickle
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from statsmodels.tsa.arima.model import ARIMA

from src.infrastructure.ml.models.metrics import RegressionMetrics


# ============================================================================
# CONFIGURATION
# ============================================================================

MINIMUM_HISTORY_DAYS = 20
"""
Minimum number of historical observations required by the INVEST IQ
ARIMA model contract.

The unit-test and model-selection contract defines 20 observations as
the minimum acceptable history.

The training implementation still ensures that the chronological
training portion contains enough observations for the configured
ARIMA order.
"""

DEFAULT_ORDER = (5, 1, 0)
"""
Default ARIMA configuration:

    p = 5
    d = 1
    q = 0

The first difference helps handle a non-stationary price series.
"""


# ============================================================================
# TRAIN RESULT
# ============================================================================


@dataclass(frozen=True, slots=True)
class ArimaTrainResult:
    """
    Result returned after ARIMA training.
    """

    metrics: RegressionMetrics

    order: tuple[int, int, int]


# ============================================================================
# MODEL
# ============================================================================


class ArimaModel:
    """
    Wrapper around statsmodels ARIMA.

    The wrapper hides statsmodels-specific implementation details from
    the application and decision layers.
    """

    def __init__(
        self,
        order: tuple[int, int, int] = DEFAULT_ORDER,
    ) -> None:
        self._validate_order(order)

        self._order = order

        self._fitted_result: Any | None = None

    # ========================================================================
    # ORDER VALIDATION
    # ========================================================================

    @staticmethod
    def _validate_order(
        order: tuple[int, int, int],
    ) -> None:
        """
        Validate the ARIMA (p, d, q) configuration.
        """

        if not isinstance(order, tuple):
            raise TypeError(
                "ARIMA order must be a tuple of (p, d, q)."
            )

        if len(order) != 3:
            raise ValueError(
                "ARIMA order must contain exactly three values: "
                "(p, d, q)."
            )

        p, d, q = order

        if not all(
            isinstance(value, int)
            for value in order
        ):
            raise TypeError(
                "ARIMA order values p, d, and q must all be integers."
            )

        if p < 0 or d < 0 or q < 0:
            raise ValueError(
                "ARIMA order values p, d, and q must be non-negative."
            )

    # ========================================================================
    # HISTORY CHECK
    # ========================================================================

    @staticmethod
    def has_sufficient_history(
        n_rows: int,
    ) -> bool:
        """
        Determine whether enough historical observations exist for ARIMA.
        """

        if not isinstance(n_rows, int):
            return False

        return n_rows >= MINIMUM_HISTORY_DAYS

    # ========================================================================
    # INPUT VALIDATION
    # ========================================================================

    @staticmethod
    def _validate_prices(
        close_prices: npt.NDArray[np.float64],
    ) -> np.ndarray:
        """
        Validate and normalize the input price series.
        """

        prices = np.asarray(
            close_prices,
            dtype=np.float64,
        )

        if prices.ndim != 1:
            raise ValueError(
                "ARIMA close_prices must be a one-dimensional array."
            )

        if len(prices) == 0:
            raise ValueError(
                "ARIMA close_prices cannot be empty."
            )

        if not np.all(
            np.isfinite(prices)
        ):
            raise ValueError(
                "ARIMA close_prices contain NaN or infinite values."
            )

        if np.any(
            prices <= 0
        ):
            raise ValueError(
                "ARIMA close_prices must contain strictly positive prices."
            )

        return prices

    # ========================================================================
    # TRAIN
    # ========================================================================

    def train(
        self,
        close_prices: npt.NDArray[np.float64],
    ) -> ArimaTrainResult:
        """
        Train ARIMA using a chronological train/validation split.

        The validation set is always later in time than the training set.

        After validation, the final serving model is refitted using the
        complete historical dataset.
        """

        prices = self._validate_prices(
            close_prices
        )

        # --------------------------------------------------------------------
        # MINIMUM HISTORY
        # --------------------------------------------------------------------

        if len(prices) < MINIMUM_HISTORY_DAYS:
            raise ValueError(
                f"ARIMA training requires at least "
                f"{MINIMUM_HISTORY_DAYS} observations, "
                f"got {len(prices)}."
            )

        # --------------------------------------------------------------------
        # CHRONOLOGICAL VALIDATION SPLIT
        # --------------------------------------------------------------------
        #
        # IMPORTANT:
        #
        # Do not require MINIMUM_HISTORY_DAYS observations inside the
        # training split.
        #
        # MINIMUM_HISTORY_DAYS describes the complete dataset.
        #
        # The previous implementation incorrectly required:
        #
        #     max(MINIMUM_HISTORY_DAYS, p + d + q + 5)
        #
        # inside the training portion.
        #
        # With exactly 20 observations that created an impossible
        # requirement of 30 training rows.
        #
        # Instead, the chronological split is kept at approximately 80/20.
        # A small safety floor is used for statsmodels.
        # --------------------------------------------------------------------

        split_index = int(
            len(prices) * 0.80
        )

        # Keep enough observations for the configured ARIMA model.
        #
        # For the default (5, 1, 0), this evaluates to 11.
        minimum_training_rows = max(
            self._order[0]
            + self._order[1]
            + self._order[2]
            + 5,
            10,
        )

        split_index = max(
            split_index,
            minimum_training_rows,
        )

        # Always leave at least one observation for validation.
        split_index = min(
            split_index,
            len(prices) - 1,
        )

        train_prices = prices[
            :split_index
        ]

        validation_prices = prices[
            split_index:
        ]

        if len(train_prices) < minimum_training_rows:
            raise ValueError(
                "Insufficient observations for ARIMA training after "
                "creating the validation split. "
                f"Required at least {minimum_training_rows}, "
                f"got {len(train_prices)}."
            )

        # --------------------------------------------------------------------
        # VALIDATION MODEL
        # --------------------------------------------------------------------

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            validation_model = ARIMA(
                train_prices,
                order=self._order,
            )

            validation_result = (
                validation_model.fit()
            )

        # --------------------------------------------------------------------
        # VALIDATION FORECAST
        # --------------------------------------------------------------------

        if len(validation_prices) > 0:
            validation_forecast = (
                validation_result.forecast(
                    steps=len(validation_prices)
                )
            )

            validation_predictions = np.asarray(
                validation_forecast,
                dtype=np.float64,
            )

            if not np.all(
                np.isfinite(validation_predictions)
            ):
                raise RuntimeError(
                    "ARIMA produced NaN or infinite validation "
                    "forecast values."
                )

            metrics = RegressionMetrics.compute(
                validation_prices,
                validation_predictions,
            )

        else:
            # Defensive fallback.
            #
            # The normal split always leaves at least one validation
            # observation, but this keeps the method robust if the split
            # strategy changes later.

            fitted_values = np.asarray(
                validation_result.fittedvalues,
                dtype=np.float64,
            )

            actual = train_prices[
                -len(fitted_values):
            ]

            valid_mask = (
                np.isfinite(fitted_values)
                & np.isfinite(actual)
            )

            if not np.any(
                valid_mask
            ):
                raise RuntimeError(
                    "ARIMA could not produce valid validation predictions."
                )

            metrics = RegressionMetrics.compute(
                actual[valid_mask],
                fitted_values[valid_mask],
            )

        # --------------------------------------------------------------------
        # FINAL MODEL
        # --------------------------------------------------------------------
        #
        # The final serving model is trained using ALL available historical
        # observations.
        #
        # This model is persisted by TrainModelUseCase.
        #
        # DecisionEngine only loads and predicts.
        # --------------------------------------------------------------------

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            full_model = ARIMA(
                prices,
                order=self._order,
            )

            self._fitted_result = (
                full_model.fit()
            )

        return ArimaTrainResult(
            metrics=metrics,
            order=self._order,
        )

    # ========================================================================
    # FORECAST
    # ========================================================================

    def predict_next(
        self,
        steps_ahead: int = 1,
    ) -> list[float]:
        """
        Forecast the next `steps_ahead` observations.
        """

        if self._fitted_result is None:
            raise RuntimeError(
                "train() must be called before predict_next()."
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

        forecast = (
            self._fitted_result.forecast(
                steps=steps_ahead
            )
        )

        predictions = np.asarray(
            forecast,
            dtype=np.float64,
        )

        if len(predictions) != steps_ahead:
            raise RuntimeError(
                "ARIMA returned an unexpected number of forecast values."
            )

        if not np.all(
            np.isfinite(predictions)
        ):
            raise RuntimeError(
                "ARIMA produced NaN or infinite forecast values."
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
    # MODEL STATUS
    # ========================================================================

    @property
    def is_fitted(self) -> bool:
        """
        Whether this instance currently contains a fitted ARIMA model.
        """

        return (
            self._fitted_result is not None
        )

    # ========================================================================
    # ORDER
    # ========================================================================

    @property
    def order(
        self,
    ) -> tuple[int, int, int]:
        """
        Return the configured ARIMA order.
        """

        return self._order

    # ========================================================================
    # SAVE
    # ========================================================================

    def save(
        self,
        path: str | Path,
    ) -> None:
        """
        Persist the fitted ARIMA model.

        The artifact contains:

            - model type
            - artifact version
            - ARIMA order
            - fitted statsmodels result
        """

        if self._fitted_result is None:
            raise RuntimeError(
                "train() must be called before save()."
            )

        artifact_path = Path(
            path
        )

        artifact_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "model_type": "ARIMA",
            "model_version": 1,
            "order": self._order,
            "fitted_result": self._fitted_result,
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
    ) -> ArimaModel:
        """
        Load a previously trained ARIMA artifact.

        Artifacts are trusted local model files produced by INVEST IQ.
        """

        artifact_path = Path(
            path
        )

        # --------------------------------------------------------------------
        # PATH VALIDATION
        # --------------------------------------------------------------------

        if not artifact_path.exists():
            raise FileNotFoundError(
                f"ARIMA artifact does not exist: "
                f"{artifact_path}"
            )

        if not artifact_path.is_file():
            raise ValueError(
                f"ARIMA artifact path is not a file: "
                f"{artifact_path}"
            )

        # --------------------------------------------------------------------
        # LOAD ARTIFACT
        # --------------------------------------------------------------------

        with artifact_path.open(
            "rb"
        ) as file:
            payload = pickle.load(
                file
            )

        # --------------------------------------------------------------------
        # PAYLOAD VALIDATION
        # --------------------------------------------------------------------

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "Invalid ARIMA artifact format."
            )

        if (
            payload.get("model_type")
            != "ARIMA"
        ):
            raise ValueError(
                "Artifact does not contain an ARIMA model."
            )

        artifact_version = payload.get(
            "model_version"
        )

        if artifact_version != 1:
            raise ValueError(
                "Unsupported ARIMA artifact version: "
                f"{artifact_version}"
            )

        order = payload.get(
            "order"
        )

        fitted_result = payload.get(
            "fitted_result"
        )

        if order is None:
            raise ValueError(
                "ARIMA artifact is missing model order."
            )

        if fitted_result is None:
            raise ValueError(
                "ARIMA artifact is missing the fitted model result."
            )

        # --------------------------------------------------------------------
        # ORDER VALIDATION
        # --------------------------------------------------------------------

        try:
            normalized_order = tuple(
                int(value)
                for value in order
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "ARIMA artifact contains an invalid model order."
            ) from exc

        if len(normalized_order) != 3:
            raise ValueError(
                "ARIMA artifact order must contain exactly "
                "three values."
            )

        # --------------------------------------------------------------------
        # CREATE MODEL INSTANCE
        # --------------------------------------------------------------------

        model = cls(
            order=normalized_order,
        )

        model._fitted_result = (
            fitted_result
        )

        return model