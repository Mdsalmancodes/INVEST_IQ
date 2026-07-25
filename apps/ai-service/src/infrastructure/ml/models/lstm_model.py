"""LSTM price-forecasting model — Document 4 §10.2's sequence model,
captures temporal patterns over a 60-day lookback window (Document 4
§10.1a's stated minimum history: 90 trading days to have a meaningful
train/validation split over that lookback).

Architecture: a single nn.LSTM layer + linear head, trained on the scaled
close-price sequence (this phase's minimal-but-real implementation — not a
multi-feature sequence model; the tree-based models (Random Forest,
XGBoost) are what consume the full engineered feature set per Document 4
§10.2 step 2's "captures fundamental/sentiment interactions the sequence
models can't see directly" division of labor).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import torch
from torch import nn

from src.infrastructure.ml.models.metrics import RegressionMetrics

LOOKBACK_WINDOW = 60
MINIMUM_HISTORY_DAYS = 90
"""Per Document 4 §10.1a's LSTM row: '90 trading days' minimum, below
which LSTM is excluded from the ensemble entirely."""


class _LstmNet(nn.Module):
    def __init__(self, hidden_size: int = 32, num_layers: int = 1) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=1, hidden_size=hidden_size, num_layers=num_layers, batch_first=True
        )
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        output, _ = self.lstm(x)
        last_step = output[:, -1, :]
        result: torch.Tensor = self.head(last_step)
        return result


@dataclass(frozen=True, slots=True)
class LstmTrainResult:
    metrics: RegressionMetrics
    artifact_path: str
    price_mean: float
    price_std: float


class LstmModel:
    """Wraps `_LstmNet` with the scaling/windowing/persistence concerns a
    caller (the training pipeline, the decision engine) shouldn't have to
    know about — mirrors how core-api's SqlAlchemy*Repository classes hide
    ORM mechanics behind a plain method interface."""

    def __init__(self, hidden_size: int = 32, num_layers: int = 1) -> None:
        self._hidden_size = hidden_size
        self._num_layers = num_layers
        self._net = _LstmNet(hidden_size=hidden_size, num_layers=num_layers)
        self._price_mean = 0.0
        self._price_std = 1.0

    @staticmethod
    def has_sufficient_history(n_rows: int) -> bool:
        return n_rows >= MINIMUM_HISTORY_DAYS

    def _build_windows(
        self, prices: npt.NDArray[np.float64]
    ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        x_windows = []
        y_targets = []
        for i in range(LOOKBACK_WINDOW, len(prices)):
            x_windows.append(prices[i - LOOKBACK_WINDOW : i])
            y_targets.append(prices[i])
        return np.array(x_windows), np.array(y_targets)

    def train(
        self,
        close_prices: npt.NDArray[np.float64],
        epochs: int = 30,
        learning_rate: float = 0.01,
    ) -> LstmTrainResult:
        if len(close_prices) < LOOKBACK_WINDOW + 10:
            raise ValueError(
                f"LSTM training requires at least {LOOKBACK_WINDOW + 10} rows, "
                f"got {len(close_prices)}"
            )

        self._price_mean = float(np.mean(close_prices))
        self._price_std = float(np.std(close_prices)) or 1.0
        normalized = (close_prices - self._price_mean) / self._price_std

        x_windows, y_targets = self._build_windows(normalized)
        split = max(1, int(len(x_windows) * 0.8))
        x_train, x_val = x_windows[:split], x_windows[split:]
        y_train, y_val = y_targets[:split], y_targets[split:]

        if len(x_val) == 0:
            x_val, y_val = x_train, y_train

        x_train_t = torch.tensor(x_train, dtype=torch.float32).unsqueeze(-1)
        y_train_t = torch.tensor(y_train, dtype=torch.float32).unsqueeze(-1)

        optimizer = torch.optim.Adam(self._net.parameters(), lr=learning_rate)
        loss_fn = nn.MSELoss()

        self._net.train()
        for _ in range(epochs):
            optimizer.zero_grad()
            predictions = self._net(x_train_t)
            loss = loss_fn(predictions, y_train_t)
            loss.backward()
            optimizer.step()

        self._net.eval()
        with torch.no_grad():
            x_val_t = torch.tensor(x_val, dtype=torch.float32).unsqueeze(-1)
            val_predictions_norm = self._net(x_val_t).squeeze(-1).numpy()

        val_predictions = val_predictions_norm * self._price_std + self._price_mean
        val_actual = y_val * self._price_std + self._price_mean
        metrics = RegressionMetrics.compute(val_actual, val_predictions)

        return LstmTrainResult(
            metrics=metrics,
            artifact_path="",  # populated by caller after save()
            price_mean=self._price_mean,
            price_std=self._price_std,
        )

    def predict_next(
        self, recent_close_prices: npt.NDArray[np.float64], steps_ahead: int = 1
    ) -> list[float]:
        """Autoregressive multi-step forecast: each predicted price is fed
        back in as the newest element of the next window, per horizon
        step. `recent_close_prices` must contain at least LOOKBACK_WINDOW
        most-recent closes."""
        if len(recent_close_prices) < LOOKBACK_WINDOW:
            raise ValueError(
                f"predict_next requires at least {LOOKBACK_WINDOW} recent prices, "
                f"got {len(recent_close_prices)}"
            )

        window = list(
            (recent_close_prices[-LOOKBACK_WINDOW:] - self._price_mean) / self._price_std
        )
        self._net.eval()
        predictions: list[float] = []
        with torch.no_grad():
            for _ in range(steps_ahead):
                x = torch.tensor([window], dtype=torch.float32).unsqueeze(-1)
                next_norm = self._net(x).item()
                predictions.append(next_norm * self._price_std + self._price_mean)
                window = window[1:] + [next_norm]
        return predictions

    def save(self, path: str | Path) -> None:
        artifact_path = Path(path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self._net.state_dict(),
                "price_mean": self._price_mean,
                "price_std": self._price_std,
                "hidden_size": self._hidden_size,
                "num_layers": self._num_layers,
            },
            artifact_path,
        )

    @classmethod
    def load(cls, path: str | Path) -> LstmModel:
        checkpoint = torch.load(path, weights_only=False)
        model = cls(
            hidden_size=checkpoint["hidden_size"], num_layers=checkpoint["num_layers"]
        )
        model._net.load_state_dict(checkpoint["state_dict"])
        model._price_mean = checkpoint["price_mean"]
        model._price_std = checkpoint["price_std"]
        model._net.eval()
        return model
