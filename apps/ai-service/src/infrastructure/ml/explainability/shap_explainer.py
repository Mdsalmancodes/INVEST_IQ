"""ShapExplainerService — Document 4 §10.9's Explainable AI integration.

Per the founder's Phase 7 instruction: "Implement SHAP. Every
recommendation must include: Feature Importance, Model Contribution,
Explanation, Confidence, Reasoning." SHAP is applied to the tree-based
ensemble members (Random Forest, XGBoost) specifically — per Document 4
§10.9's own text, "SHAP values computed for the tree-based ensemble
member (SHAP is natively efficient for tree models via TreeExplainer)."
LSTM/ARIMA/Prophet/FinBERT do not receive SHAP explanations (the
architecture doc names LIME as the fallback for the neural/LSTM
component specifically, but LIME is not in the founder's explicit
Phase 7 requirement list, so it is not built this phase — the
DecisionEngine's existing weighted-signal reasoning already covers those
members' contribution to the final verdict, per Document 4 §10.1's
"model version tag" + reasoning invariant, which does not require every
member to use the identical explanation method).
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import numpy.typing as npt
import pandas as pd
import shap

from src.domain.ml.value_objects import ExplainabilityPayload, FeatureContribution


class _HasUnderlyingTreeModel(Protocol):
    """Structural typing for RandomForestModel/XgboostModel — both expose
    a private `_model` attribute holding the real fitted sklearn/xgboost
    estimator SHAP's TreeExplainer needs. Modeled as a read-only property
    (not a plain attribute) so mypy's structural Protocol matching does
    not require the concrete classes' `_model` attribute type to be
    exactly `object` (attribute types are checked invariantly; property
    getters are checked covariantly, which is what we actually want
    here — any concrete estimator type satisfies "produces an object")."""

    @property
    def _model(self) -> object: ...


class ShapExplainerService:
    """Per Document 4 §10.9's exact code example:

    ```python
    class ShapExplainerService:
        def __init__(self, model: XGBoostModel):
            self._explainer = shap.TreeExplainer(model.underlying)

        def explain(self, feature_vector: FeatureVector) -> ExplainabilityPayload:
            ...
    ```

    Adapted here to accept any tree-based model wrapper exposing its
    fitted estimator (Random Forest or XGBoost — both are valid per
    Document 4 §10.2's "tree-based ensemble member" description, not
    XGBoost exclusively), and to accept a plain pandas DataFrame feature
    vector (matching this phase's `FeatureEngineer` output shape) rather
    than a separate `FeatureVector` domain type, since this phase's
    feature matrix is already a well-typed pandas DataFrame.
    """

    def __init__(self, model: _HasUnderlyingTreeModel) -> None:
        self._explainer = shap.TreeExplainer(model._model)  # noqa: SLF001 — intentional access to the wrapped estimator, the whole point of this adapter

    def explain(self, feature_row: pd.DataFrame) -> ExplainabilityPayload:
        """`feature_row` must be a single-row DataFrame (the feature
        vector for one instrument at one point in time) with the same
        columns the underlying model was trained on. Returns the top 8
        feature contributions by absolute SHAP value, matching Document 4
        §10.9's 'top 8 for UI readability' example exactly."""
        if len(feature_row) != 1:
            raise ValueError(
                f"ShapExplainerService.explain() requires exactly one row, got {len(feature_row)}"
            )

        shap_values = self._explainer.shap_values(feature_row)
        # For a binary classifier, shap_values may be returned as a list
        # of per-class arrays (older SHAP/estimator combinations) or as a
        # single 2D array with the positive class already selected
        # (newer combinations) — both are handled explicitly rather than
        # assuming one shape, since silently mis-indexing here would
        # attribute contributions to the wrong class.
        values = self._extract_positive_class_values(shap_values)

        feature_names = list(feature_row.columns)
        contributions = [
            FeatureContribution(name=feature_names[i], value=float(values[i]))
            for i in range(len(feature_names))
        ]
        contributions.sort(key=lambda c: abs(c.value), reverse=True)

        base_value = self._extract_base_value()

        return ExplainabilityPayload(
            top_contributions=tuple(contributions[:8]),
            base_value=base_value,
            method="shap_tree_explainer",
            reasoning=_build_shap_reasoning(contributions[:8]),
        )

    def _extract_positive_class_values(self, shap_values: object) -> npt.NDArray[np.float64]:
        if isinstance(shap_values, list):
            # Binary classifier, list-of-arrays form: index 1 is the
            # positive ("upward"/"buy") class, matching how
            # RandomForestModel/XgboostModel both treat class 1 as
            # upward movement.
            positive_class_values = shap_values[1] if len(shap_values) > 1 else shap_values[0]
            row: npt.NDArray[np.float64] = np.asarray(positive_class_values, dtype=np.float64)[0]
            return row

        values_array = np.asarray(shap_values, dtype=np.float64)
        if values_array.ndim == 3:
            # (n_samples, n_features, n_classes) form — select the
            # positive class's contributions for the single row.
            selected: npt.NDArray[np.float64] = (
                values_array[0, :, 1] if values_array.shape[2] > 1 else values_array[0, :, 0]
            )
            return selected
        # (n_samples, n_features) form — already the positive class (or a
        # regressor's single output).
        final: npt.NDArray[np.float64] = values_array[0]
        return final

    def _extract_base_value(self) -> float:
        expected_value = self._explainer.expected_value
        if isinstance(expected_value, list | np.ndarray):
            values = np.asarray(expected_value)
            return float(values[1]) if values.shape[0] > 1 else float(values[0])
        return float(expected_value)


def _build_shap_reasoning(top_contributions: list[FeatureContribution]) -> str:
    if not top_contributions:
        return "No feature contributions were computed."
    parts = [
        f"{c.name} ({'+' if c.direction == 'positive' else ''}{c.value:.4f})"
        for c in top_contributions
    ]
    return "Top SHAP feature contributions: " + ", ".join(parts) + "."
