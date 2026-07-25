"""Unit tests for ShapExplainerService. Uses REAL trained
RandomForestModel/XgboostModel instances (via FeatureEngineer's real
engineered feature matrix) — not mocked, matching this codebase's
established convention for AI model tests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.infrastructure.ml.explainability.shap_explainer import ShapExplainerService
from src.infrastructure.ml.features.engineer import (
    FeatureEngineer,
    classification_labels_from_returns,
)
from src.infrastructure.ml.models.random_forest_model import RandomForestModel
from src.infrastructure.ml.models.xgboost_model import XgboostModel


def _ohlcv(n: int = 150, seed: int = 31) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=0.05, scale=1.0, size=n)
    close = pd.Series(100 + np.cumsum(steps))
    high = close + 1.0
    low = close - 1.0
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = pd.Series(np.full(n, 500_000.0))
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


def _training_data(n: int = 150) -> tuple[pd.DataFrame, pd.Series]:
    ohlcv = _ohlcv(n)
    engineer = FeatureEngineer()
    matrix = engineer.build(ohlcv)
    clean_features = FeatureEngineer.handle_missing_values(matrix.raw)
    labels = classification_labels_from_returns(ohlcv["close"], horizon_days=1)
    combined = clean_features.copy()
    combined["_label"] = labels
    combined = combined.dropna()
    y = combined.pop("_label")
    return combined, y


class TestShapExplainerServiceWithRandomForest:
    def test_explains_a_single_feature_row(self) -> None:
        features, labels = _training_data()
        model = RandomForestModel()
        model.train(features, labels)

        service = ShapExplainerService(model)
        payload = service.explain(features.iloc[[-1]])

        assert payload.method == "shap_tree_explainer"
        assert len(payload.top_contributions) <= 8
        assert payload.reasoning != ""

    def test_contributions_are_sorted_by_absolute_value_descending(self) -> None:
        features, labels = _training_data()
        model = RandomForestModel()
        model.train(features, labels)

        service = ShapExplainerService(model)
        payload = service.explain(features.iloc[[-1]])

        magnitudes = [abs(c.value) for c in payload.top_contributions]
        assert magnitudes == sorted(magnitudes, reverse=True)

    def test_rejects_multi_row_input(self) -> None:
        features, labels = _training_data()
        model = RandomForestModel()
        model.train(features, labels)

        service = ShapExplainerService(model)
        with pytest.raises(ValueError, match="requires exactly one row"):
            service.explain(features.iloc[-3:])


class TestShapExplainerServiceWithXgboost:
    def test_explains_a_single_feature_row(self) -> None:
        features, labels = _training_data()
        model = XgboostModel()
        model.train(features, labels)

        service = ShapExplainerService(model)
        payload = service.explain(features.iloc[[-1]])

        assert payload.method == "shap_tree_explainer"
        assert len(payload.top_contributions) <= 8

    def test_contribution_feature_names_match_training_columns(self) -> None:
        features, labels = _training_data()
        model = XgboostModel()
        model.train(features, labels)

        service = ShapExplainerService(model)
        payload = service.explain(features.iloc[[-1]])

        contribution_names = {c.name for c in payload.top_contributions}
        assert contribution_names.issubset(set(features.columns))

    def test_reasoning_mentions_top_contribution_name(self) -> None:
        features, labels = _training_data()
        model = XgboostModel()
        model.train(features, labels)

        service = ShapExplainerService(model)
        payload = service.explain(features.iloc[[-1]])

        assert payload.top_contributions[0].name in payload.reasoning
