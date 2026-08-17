"""
LSTM price-forecasting model for INVEST IQ.

Responsibilities
----------------
- Learn temporal patterns from historical closing prices.
- Use a 60-observation lookback window.
- Produce recursive multi-step price forecasts.
- Perform chronological train/validation splitting.
- Prevent normalization leakage from validation data.
- Persist model weights and normalization metadata.
- Support CUDA when available, with CPU fallback.
- Provide validation metrics for model registry tracking.

Important
---------
This model intentionally consumes closing-price history only.

Random Forest and XGBoost consume the engineered technical-indicator
feature matrix.

The LSTM therefore acts as the sequence/time-series component of the
hybrid ensemble rather than duplicating the tree-based feature pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import torch
from torch import nn

from src.infrastructure.ml.models.metrics import RegressionMetrics


# ============================================================================
# CONFIGURATION
# ============================================================================

LOOKBACK_WINDOW = 60

# Minimum history required by the current INVEST IQ test suite and model
# contract.
#
# With 100 observations and a 60-observation lookback:
#
#     80 training observations
#     - 60 lookback
#     = 20 training windows
#
# This exactly satisfies MINIMUM_TRAINING_WINDOWS.
MINIMUM_HISTORY_DAYS = 90

DEFAULT_EPOCHS = 50

DEFAULT_LEARNING_RATE = 0.001

DEFAULT_HIDDEN_SIZE = 64

DEFAULT_NUM_LAYERS = 1

DEFAULT_VALIDATION_RATIO = 0.20

EARLY_STOPPING_PATIENCE = 8

MINIMUM_TRAINING_WINDOWS = 20

RANDOM_SEED = 42


# ============================================================================
# REPRODUCIBILITY
# ============================================================================


def _set_random_seed() -> None:
    """
    Configure deterministic random seeds.

    The seed controls NumPy and PyTorch initialization.
    """

    np.random.seed(RANDOM_SEED)

    torch.manual_seed(
        RANDOM_SEED
    )

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(
            RANDOM_SEED
        )


# ============================================================================
# DEVICE
# ============================================================================


def _get_device() -> torch.device:
    """
    Select CUDA when available, otherwise CPU.
    """

    if torch.cuda.is_available():
        return torch.device("cuda")

    return torch.device("cpu")


# ============================================================================
# NETWORK
# ============================================================================


class _LstmNet(nn.Module):
    """
    Small LSTM regression network.

    Input shape:
        [batch, sequence_length, 1]

    Output shape:
        [batch, 1]
    """

    def __init__(
        self,
        hidden_size: int = DEFAULT_HIDDEN_SIZE,
        num_layers: int = DEFAULT_NUM_LAYERS,
    ) -> None:
        super().__init__()

        self.lstm = nn.LSTM(
            input_size=1,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=(
                0.0
                if num_layers == 1
                else 0.1
            ),
        )

        self.head = nn.Linear(
            hidden_size,
            1,
        )

    def forward(
        self,
        x: torch.Tensor,
    ) -> torch.Tensor:

        output, _ = self.lstm(x)

        last_step = output[:, -1, :]

        return self.head(last_step)


# ============================================================================
# TRAIN RESULT
# ============================================================================


@dataclass(frozen=True, slots=True)
class LstmTrainResult:
    """
    Result returned by LSTM training.
    """

    metrics: RegressionMetrics

    artifact_path: str

    price_mean: float

    price_std: float

    training_windows: int

    validation_windows: int

    epochs_completed: int

    device: str


# ============================================================================
# MODEL
# ============================================================================


class LstmModel:
    """
    Production-oriented wrapper around the LSTM network.

    The wrapper owns:

        - normalization
        - window creation
        - training
        - validation
        - inference
        - persistence
        - device management
    """

    def __init__(
        self,
        hidden_size: int = DEFAULT_HIDDEN_SIZE,
        num_layers: int = DEFAULT_NUM_LAYERS,
    ) -> None:

        if not isinstance(
            hidden_size,
            int,
        ):
            raise TypeError(
                "hidden_size must be an integer."
            )

        if hidden_size <= 0:
            raise ValueError(
                "hidden_size must be greater than zero."
            )

        if not isinstance(
            num_layers,
            int,
        ):
            raise TypeError(
                "num_layers must be an integer."
            )

        if num_layers <= 0:
            raise ValueError(
                "num_layers must be greater than zero."
            )

        self._hidden_size = hidden_size

        self._num_layers = num_layers

        self._net = _LstmNet(
            hidden_size=hidden_size,
            num_layers=num_layers,
        )

        self._device = _get_device()

        self._net.to(self._device)

        self._price_mean = 0.0

        self._price_std = 1.0

        self._is_fitted = False

    # ========================================================================
    # HISTORY REQUIREMENT
    # ========================================================================

    @staticmethod
    def has_sufficient_history(
        n_rows: int,
    ) -> bool:
        """
        Return whether enough observations are available for training.
        """

        return n_rows >= MINIMUM_HISTORY_DAYS

    # ========================================================================
    # INPUT VALIDATION
    # ========================================================================

    @staticmethod
    def _validate_prices(
        close_prices: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        """
        Validate closing-price input.
        """

        prices = np.asarray(
            close_prices,
            dtype=np.float64,
        )

        if prices.ndim != 1:
            raise ValueError(
                "close_prices must be a one-dimensional array."
            )

        if len(prices) == 0:
            raise ValueError(
                "close_prices cannot be empty."
            )

        if not np.isfinite(prices).all():
            raise ValueError(
                "close_prices contains NaN or infinite values."
            )

        if (prices <= 0).any():
            raise ValueError(
                "close_prices must contain strictly positive prices."
            )

        return prices

    # ========================================================================
    # WINDOW CREATION
    # ========================================================================

    @staticmethod
    def _build_windows(
        prices: npt.NDArray[np.float64],
    ) -> tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ]:
        """
        Convert a normalized price series into supervised LSTM sequences.

        For every time t:

            X = prices[t-60:t]
            y = prices[t]
        """

        if len(prices) <= LOOKBACK_WINDOW:
            raise ValueError(
                "Not enough prices to construct "
                "an LSTM training window."
            )

        x_windows: list[
            npt.NDArray[np.float64]
        ] = []

        y_targets: list[float] = []

        for index in range(
            LOOKBACK_WINDOW,
            len(prices),
        ):

            x_windows.append(
                prices[
                    index - LOOKBACK_WINDOW:index
                ]
            )

            y_targets.append(
                float(prices[index])
            )

        return (
            np.asarray(
                x_windows,
                dtype=np.float64,
            ),
            np.asarray(
                y_targets,
                dtype=np.float64,
            ),
        )

    # ========================================================================
    # NORMALIZATION
    # ========================================================================

    @staticmethod
    def _fit_normalization(
        training_prices: npt.NDArray[np.float64],
    ) -> tuple[float, float]:
        """
        Fit normalization ONLY on the training portion.

        Validation observations are never used to calculate mean/std.
        """

        mean = float(
            np.mean(training_prices)
        )

        std = float(
            np.std(training_prices)
        )

        if not np.isfinite(mean):
            raise ValueError(
                "Unable to calculate a finite price mean."
            )

        if (
            not np.isfinite(std)
            or std <= 1e-12
        ):
            std = 1.0

        return mean, std

    @staticmethod
    def _normalize(
        prices: npt.NDArray[np.float64],
        mean: float,
        std: float,
    ) -> npt.NDArray[np.float64]:

        if not np.isfinite(mean):
            raise ValueError(
                "Normalization mean must be finite."
            )

        if (
            not np.isfinite(std)
            or std <= 0
        ):
            raise ValueError(
                "Normalization standard deviation must be positive."
            )

        return (
            prices - mean
        ) / std

    @staticmethod
    def _denormalize(
        prices: npt.NDArray[np.float64],
        mean: float,
        std: float,
    ) -> npt.NDArray[np.float64]:

        return (
            prices * std
        ) + mean

    # ========================================================================
    # TRAIN
    # ========================================================================

    def train(
        self,
        close_prices: npt.NDArray[np.float64],
        epochs: int = DEFAULT_EPOCHS,
        learning_rate: float = DEFAULT_LEARNING_RATE,
        validation_ratio: float = DEFAULT_VALIDATION_RATIO,
        patience: int = EARLY_STOPPING_PATIENCE,
    ) -> LstmTrainResult:
        """
        Train the LSTM using chronological validation.

        Normalization statistics are calculated only from the training
        portion to prevent validation leakage.
        """

        prices = self._validate_prices(
            close_prices
        )

        if len(prices) < MINIMUM_HISTORY_DAYS:
            raise ValueError(
                f"LSTM training requires at least "
                f"{MINIMUM_HISTORY_DAYS} rows, "
                f"got {len(prices)}."
            )

        if not isinstance(
            epochs,
            int,
        ):
            raise TypeError(
                "epochs must be an integer."
            )

        if epochs <= 0:
            raise ValueError(
                "epochs must be greater than zero."
            )

        if learning_rate <= 0:
            raise ValueError(
                "learning_rate must be greater than zero."
            )

        if not (
            0.05
            <= validation_ratio
            < 0.5
        ):
            raise ValueError(
                "validation_ratio must be between "
                "0.05 and 0.49."
            )

        if not isinstance(
            patience,
            int,
        ):
            raise TypeError(
                "patience must be an integer."
            )

        if patience <= 0:
            raise ValueError(
                "patience must be greater than zero."
            )

        _set_random_seed()

        # --------------------------------------------------------------------
        # CHRONOLOGICAL SPLIT
        # --------------------------------------------------------------------

        split_index = int(
            len(prices)
            * (1.0 - validation_ratio)
        )

        # We need at least:
        #
        # LOOKBACK_WINDOW + MINIMUM_TRAINING_WINDOWS
        #
        # observations in the training section.
        minimum_split_index = (
            LOOKBACK_WINDOW
            + MINIMUM_TRAINING_WINDOWS
        )

        if split_index < minimum_split_index:

            split_index = minimum_split_index

        # We must leave at least one validation observation.
        split_index = min(
            split_index,
            len(prices) - 1,
        )

        if split_index <= LOOKBACK_WINDOW:
            raise ValueError(
                "Training portion is too small for "
                "the configured LSTM lookback window."
            )

        training_prices = prices[:split_index]

        validation_prices = prices[split_index:]

        if len(validation_prices) == 0:
            raise ValueError(
                "LSTM training requires at least one "
                "validation observation."
            )

        # --------------------------------------------------------------------
        # NORMALIZATION
        # --------------------------------------------------------------------

        self._price_mean, self._price_std = (
            self._fit_normalization(
                training_prices
            )
        )

        normalized_training_prices = (
            self._normalize(
                training_prices,
                self._price_mean,
                self._price_std,
            )
        )

        # --------------------------------------------------------------------
        # TRAINING WINDOWS
        # --------------------------------------------------------------------

        x_train, y_train = (
            self._build_windows(
                normalized_training_prices
            )
        )

        if len(x_train) < MINIMUM_TRAINING_WINDOWS:
            raise ValueError(
                "LSTM training produced too few "
                f"training windows: {len(x_train)}. "
                f"Need at least {MINIMUM_TRAINING_WINDOWS}."
            )

        # --------------------------------------------------------------------
        # VALIDATION WINDOWS
        # --------------------------------------------------------------------
        #
        # Include the last 60 training observations as historical context.
        # Validation targets remain strictly after the training period.
        # --------------------------------------------------------------------

        validation_context = np.concatenate(
            [
                training_prices[
                    -LOOKBACK_WINDOW:
                ],
                validation_prices,
            ]
        )

        normalized_validation_context = (
            self._normalize(
                validation_context,
                self._price_mean,
                self._price_std,
            )
        )

        x_val, y_val = (
            self._build_windows(
                normalized_validation_context
            )
        )

        if len(x_val) == 0:
            raise ValueError(
                "LSTM validation produced no validation windows."
            )

        # --------------------------------------------------------------------
        # TENSORS
        # --------------------------------------------------------------------

        x_train_tensor = torch.tensor(
            x_train,
            dtype=torch.float32,
            device=self._device,
        ).unsqueeze(-1)

        y_train_tensor = torch.tensor(
            y_train,
            dtype=torch.float32,
            device=self._device,
        ).unsqueeze(-1)

        x_val_tensor = torch.tensor(
            x_val,
            dtype=torch.float32,
            device=self._device,
        ).unsqueeze(-1)

        y_val_tensor = torch.tensor(
            y_val,
            dtype=torch.float32,
            device=self._device,
        ).unsqueeze(-1)

        # --------------------------------------------------------------------
        # RESET NETWORK
        # --------------------------------------------------------------------

        self._net = _LstmNet(
            hidden_size=self._hidden_size,
            num_layers=self._num_layers,
        ).to(self._device)

        optimizer = torch.optim.Adam(
            self._net.parameters(),
            lr=learning_rate,
        )

        loss_fn = nn.MSELoss()

        # --------------------------------------------------------------------
        # EARLY STOPPING
        # --------------------------------------------------------------------

        best_validation_loss = float("inf")

        best_state_dict: dict[
            str,
            torch.Tensor,
        ] | None = None

        epochs_without_improvement = 0

        epochs_completed = 0

        # --------------------------------------------------------------------
        # TRAINING LOOP
        # --------------------------------------------------------------------

        for epoch in range(epochs):

            epochs_completed = epoch + 1

            self._net.train()

            optimizer.zero_grad(
                set_to_none=True
            )

            train_predictions = self._net(
                x_train_tensor
            )

            train_loss = loss_fn(
                train_predictions,
                y_train_tensor,
            )

            train_loss.backward()

            torch.nn.utils.clip_grad_norm_(
                self._net.parameters(),
                max_norm=1.0,
            )

            optimizer.step()

            # ---------------------------------------------------------------
            # VALIDATION
            # ---------------------------------------------------------------

            self._net.eval()

            with torch.no_grad():

                validation_predictions = self._net(
                    x_val_tensor
                )

                validation_loss = loss_fn(
                    validation_predictions,
                    y_val_tensor,
                )

            validation_loss_value = float(
                validation_loss.item()
            )

            # ---------------------------------------------------------------
            # CHECKPOINT
            # ---------------------------------------------------------------

            if (
                validation_loss_value
                < best_validation_loss
            ):

                best_validation_loss = (
                    validation_loss_value
                )

                best_state_dict = {
                    key: value.detach()
                    .cpu()
                    .clone()
                    for key, value
                    in self._net.state_dict().items()
                }

                epochs_without_improvement = 0

            else:

                epochs_without_improvement += 1

            if (
                epochs_without_improvement
                >= patience
            ):
                break

        # --------------------------------------------------------------------
        # RESTORE BEST MODEL
        # --------------------------------------------------------------------

        if best_state_dict is None:
            raise RuntimeError(
                "LSTM training failed to produce "
                "a valid model checkpoint."
            )

        self._net.load_state_dict(
            best_state_dict
        )

        self._net.to(
            self._device
        )

        self._net.eval()

        # --------------------------------------------------------------------
        # FINAL VALIDATION PREDICTIONS
        # --------------------------------------------------------------------

        with torch.no_grad():

            validation_predictions_norm = (
                self._net(
                    x_val_tensor
                )
                .squeeze(-1)
                .detach()
                .cpu()
                .numpy()
            )

        validation_predictions = (
            self._denormalize(
                validation_predictions_norm,
                self._price_mean,
                self._price_std,
            )
        )

        validation_actual = (
            self._denormalize(
                y_val,
                self._price_mean,
                self._price_std,
            )
        )

        metrics = RegressionMetrics.compute(
            validation_actual,
            validation_predictions,
        )

        self._is_fitted = True

        return LstmTrainResult(
            metrics=metrics,
            artifact_path="",
            price_mean=self._price_mean,
            price_std=self._price_std,
            training_windows=len(x_train),
            validation_windows=len(x_val),
            epochs_completed=epochs_completed,
            device=str(self._device),
        )

    # ========================================================================
    # PREDICTION
    # ========================================================================

    def predict_next(
        self,
        recent_close_prices: npt.NDArray[np.float64],
        steps_ahead: int = 1,
    ) -> list[float]:
        """
        Produce recursive multi-step forecasts.

        The first prediction uses the latest 60 observations.

        Each subsequent prediction is fed back into the sequence window.
        """

        if not self._is_fitted:
            raise RuntimeError(
                "LstmModel must be trained or loaded "
                "before predict_next()."
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

        prices = self._validate_prices(
            recent_close_prices
        )

        if len(prices) < LOOKBACK_WINDOW:
            raise ValueError(
                "predict_next requires at least "
                f"{LOOKBACK_WINDOW} recent prices, "
                f"got {len(prices)}."
            )

        normalized_window = (
            self._normalize(
                prices[-LOOKBACK_WINDOW:],
                self._price_mean,
                self._price_std,
            )
        )

        window = list(
            normalized_window.astype(
                np.float64
            )
        )

        self._net.eval()

        predictions: list[float] = []

        with torch.no_grad():

            for _ in range(steps_ahead):

                x = torch.tensor(
                    [window],
                    dtype=torch.float32,
                    device=self._device,
                ).unsqueeze(-1)

                next_normalized = float(
                    self._net(x).item()
                )

                if not np.isfinite(
                    next_normalized
                ):
                    raise RuntimeError(
                        "LSTM produced a non-finite "
                        "normalized prediction."
                    )

                next_price = (
                    next_normalized
                    * self._price_std
                    + self._price_mean
                )

                if not np.isfinite(
                    next_price
                ):
                    raise RuntimeError(
                        "LSTM produced a non-finite "
                        "price prediction."
                    )

                next_price = max(
                    0.0,
                    float(next_price),
                )

                predictions.append(
                    next_price
                )

                window = (
                    window[1:]
                    + [next_normalized]
                )

        return predictions

    # ========================================================================
    # STATUS
    # ========================================================================

    @property
    def is_fitted(self) -> bool:
        """
        Return whether the model has been trained or loaded.
        """

        return self._is_fitted

    # ========================================================================
    # SAVE
    # ========================================================================

    def save(
        self,
        path: str | Path,
    ) -> None:
        """
        Persist the trained LSTM artifact.
        """

        if not self._is_fitted:
            raise RuntimeError(
                "train() must be called before save()."
            )

        artifact_path = Path(path)

        artifact_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        checkpoint = {
            "artifact_version": 1,
            "model_type": "lstm",
            "state_dict": {
                key: value.detach().cpu()
                for key, value
                in self._net.state_dict().items()
            },
            "price_mean": self._price_mean,
            "price_std": self._price_std,
            "hidden_size": self._hidden_size,
            "num_layers": self._num_layers,
            "lookback_window": LOOKBACK_WINDOW,
            "random_seed": RANDOM_SEED,
        }

        torch.save(
            checkpoint,
            artifact_path,
        )

    # ========================================================================
    # LOAD
    # ========================================================================

    @classmethod
    def load(
        cls,
        path: str | Path,
    ) -> LstmModel:
        """
        Load a previously trained LSTM artifact.
        """

        artifact_path = Path(path)

        if not artifact_path.exists():
            raise FileNotFoundError(
                f"LSTM artifact does not exist: "
                f"{artifact_path}"
            )

        if not artifact_path.is_file():
            raise ValueError(
                f"LSTM artifact path is not a file: "
                f"{artifact_path}"
            )

        checkpoint = torch.load(
            artifact_path,
            map_location="cpu",
            weights_only=False,
        )

        if not isinstance(
            checkpoint,
            dict,
        ):
            raise ValueError(
                "Invalid LSTM artifact format."
            )

        if checkpoint.get(
            "model_type"
        ) != "lstm":
            raise ValueError(
                "Artifact is not an LSTM model."
            )

        artifact_version = checkpoint.get(
            "artifact_version"
        )

        if artifact_version != 1:
            raise ValueError(
                "Unsupported LSTM artifact version: "
                f"{artifact_version}"
            )

        artifact_lookback = checkpoint.get(
            "lookback_window"
        )

        if artifact_lookback != LOOKBACK_WINDOW:
            raise ValueError(
                "LSTM artifact lookback window "
                f"{artifact_lookback} does not match "
                f"runtime configuration {LOOKBACK_WINDOW}."
            )

        if "hidden_size" not in checkpoint:
            raise ValueError(
                "LSTM artifact is missing hidden_size."
            )

        if "num_layers" not in checkpoint:
            raise ValueError(
                "LSTM artifact is missing num_layers."
            )

        if "state_dict" not in checkpoint:
            raise ValueError(
                "LSTM artifact is missing state_dict."
            )

        if "price_mean" not in checkpoint:
            raise ValueError(
                "LSTM artifact is missing price_mean."
            )

        if "price_std" not in checkpoint:
            raise ValueError(
                "LSTM artifact is missing price_std."
            )

        model = cls(
            hidden_size=int(
                checkpoint["hidden_size"]
            ),
            num_layers=int(
                checkpoint["num_layers"]
            ),
        )

        model._price_mean = float(
            checkpoint["price_mean"]
        )

        model._price_std = float(
            checkpoint["price_std"]
        )

        if not np.isfinite(
            model._price_mean
        ):
            raise ValueError(
                "Invalid LSTM price mean."
            )

        if (
            not np.isfinite(
                model._price_std
            )
            or model._price_std <= 0
        ):
            raise ValueError(
                "Invalid LSTM price standard deviation."
            )

        state_dict = checkpoint[
            "state_dict"
        ]

        if not isinstance(
            state_dict,
            dict,
        ):
            raise ValueError(
                "Invalid LSTM state_dict."
            )

        try:
            model._net.load_state_dict(
                state_dict
            )
        except RuntimeError as exc:
            raise ValueError(
                "LSTM artifact weights do not match "
                "the stored architecture."
            ) from exc

        model._net.to(
            model._device
        )

        model._net.eval()

        model._is_fitted = True

        return model