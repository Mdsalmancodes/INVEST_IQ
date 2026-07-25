"use client";

import { Card } from "@investiq/ui";
import { useState } from "react";

import { ADMIN_ROLES, RequireRole } from "../../auth/components/RequireRole";
import { useDeleteModel, useModelStatus, useRetrainModel, useTrainModel } from "../hooks/useAi";

const FAMILY_LABELS: Record<string, string> = {
  lstm: "LSTM",
  arima: "ARIMA",
  prophet: "Prophet",
  random_forest: "Random Forest",
  xgboost: "XGBoost",
  finbert: "FinBERT",
};

/** Families FinBERT excluded — it is always pretrained-only, never trainable (matches ModelStatus's own existing "Not trained" display note). */
const TRAINABLE_FAMILIES = ["lstm", "arima", "prophet", "random_forest", "xgboost"];

/**
 * ModelAdminPanel — Phase 8 admin-only model registry management
 * (train/retrain/delete). Gated by RequireRole(ADMIN_ROLES) — a
 * Basic/Premium user never sees this panel at all. This is genuinely
 * new UI (no train/retrain/delete controls existed in the frontend
 * before Phase 8 — confirmed via investigation prior to this task); the
 * real authorization boundary is core-api's require_role dependency on
 * the underlying /api/v1/ai/models/{status,train,retrain,{id}} routes
 * (src/presentation/routers/ai_proxy_router.py) — this component hiding
 * itself from non-admins is a UX convenience on top of that, not a
 * substitute for it.
 */
function ModelAdminPanel() {
  const [family, setFamily] = useState(TRAINABLE_FAMILIES[0] ?? "lstm");
  const [symbol, setSymbol] = useState("");
  const trainModel = useTrainModel();
  const retrainModel = useRetrainModel();
  const deleteModel = useDeleteModel();

  const isBusy = trainModel.isPending || retrainModel.isPending || deleteModel.isPending;
  const canSubmit = symbol.trim().length > 0 && !isBusy;

  const handleTrain = () => {
    if (!canSubmit) return;
    trainModel.mutate({ family, symbol: symbol.trim().toUpperCase() });
  };

  const handleRetrain = () => {
    if (!canSubmit) return;
    retrainModel.mutate({ family, symbol: symbol.trim().toUpperCase() });
  };

  const lastError = trainModel.error ?? retrainModel.error ?? deleteModel.error;

  return (
    <Card className="flex flex-col gap-3 border-primary/30">
      <h3 className="text-sm font-semibold text-text-primary">Model Administration</h3>
      <p className="text-xs text-text-secondary">
        Admin-only: train or retrain a model family for a specific symbol, or delete a model
        version from the registry using its id.
      </p>

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="admin-family-select" className="text-xs font-medium text-text-primary">
            Family
          </label>
          <select
            id="admin-family-select"
            value={family}
            onChange={(event) => setFamily(event.target.value)}
            className="h-9 rounded-md border border-primary-100 bg-surface px-2 text-sm text-text-primary"
          >
            {TRAINABLE_FAMILIES.map((familyOption) => (
              <option key={familyOption} value={familyOption}>
                {FAMILY_LABELS[familyOption] ?? familyOption}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="admin-symbol-input" className="text-xs font-medium text-text-primary">
            Symbol
          </label>
          <input
            id="admin-symbol-input"
            type="text"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value)}
            placeholder="e.g. AAPL"
            className="h-9 rounded-md border border-primary-100 bg-surface px-2 text-sm text-text-primary"
          />
        </div>

        <button
          type="button"
          onClick={handleTrain}
          disabled={!canSubmit}
          className="h-9 rounded-md bg-primary px-3 text-sm font-medium text-white disabled:opacity-50"
        >
          {trainModel.isPending ? "Training…" : "Train"}
        </button>
        <button
          type="button"
          onClick={handleRetrain}
          disabled={!canSubmit}
          className="h-9 rounded-md border border-primary px-3 text-sm font-medium text-primary disabled:opacity-50"
        >
          {retrainModel.isPending ? "Retraining…" : "Retrain"}
        </button>
      </div>

      <DeleteModelForm isBusy={isBusy} onDelete={(id) => deleteModel.mutate(id)} />

      {lastError && (
        <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
          {lastError instanceof Error ? lastError.message : "The request failed."}
        </p>
      )}
      {(trainModel.isSuccess || retrainModel.isSuccess || deleteModel.isSuccess) && (
        <p role="status" className="rounded-md bg-success/10 px-3 py-2 text-sm text-success">
          Model registry updated.
        </p>
      )}
    </Card>
  );
}

function DeleteModelForm({
  isBusy,
  onDelete,
}: {
  isBusy: boolean;
  onDelete: (modelVersionId: string) => void;
}) {
  const [modelVersionId, setModelVersionId] = useState("");

  return (
    <div className="flex flex-wrap items-end gap-2 border-t border-primary-100 pt-3">
      <div className="flex flex-col gap-1">
        <label htmlFor="admin-delete-id-input" className="text-xs font-medium text-text-primary">
          Model version id (to delete)
        </label>
        <input
          id="admin-delete-id-input"
          type="text"
          value={modelVersionId}
          onChange={(event) => setModelVersionId(event.target.value)}
          placeholder="UUID"
          className="h-9 w-72 rounded-md border border-primary-100 bg-surface px-2 text-sm text-text-primary"
        />
      </div>
      <button
        type="button"
        onClick={() => {
          if (modelVersionId.trim().length > 0) onDelete(modelVersionId.trim());
        }}
        disabled={isBusy || modelVersionId.trim().length === 0}
        className="h-9 rounded-md border border-danger px-3 text-sm font-medium text-danger disabled:opacity-50"
      >
        Delete
      </button>
    </div>
  );
}

/**
 * ModelStatus — the "Model Status" panel showing all 6 required model
 * families (Document 4 §10.8's ModelVersion lifecycle), each family's
 * active version tag/training date/validation metrics if one exists, or
 * "Not yet trained" otherwise (FinBERT is always pretrained-only — never
 * shows a trained version since it is not trainable this phase).
 */
export function ModelStatus() {
  const { data, isLoading, isError, error } = useModelStatus();

  if (isLoading) {
    return (
      <Card
        role="status"
        aria-live="polite"
        className="flex h-40 items-center justify-center animate-pulse bg-primary-50"
      >
        <span className="sr-only">Loading model status…</span>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
        Failed to load model status{error instanceof Error ? `: ${error.message}` : "."}
      </Card>
    );
  }

  if (!data) return null;

  return (
    <div className="flex flex-col gap-3">
      <Card className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-text-primary">Model Status</h3>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.families.map((family) => (
            <li
              key={family.family}
              className="flex flex-col gap-1 rounded-md border border-primary-100 p-3 text-sm"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-text-primary">
                  {FAMILY_LABELS[family.family] ?? family.family}
                </span>
                <span
                  className={`text-xs ${
                    family.active_version ? "text-success" : "text-text-secondary"
                  }`}
                >
                  {family.active_version ? "Active" : "Not trained"}
                </span>
              </div>
              {family.active_version && (
                <>
                  <p className="text-xs text-text-secondary">
                    Version: {family.active_version.version_tag}
                  </p>
                  <p className="text-xs text-text-secondary">
                    Trained: {new Date(family.active_version.trained_at).toLocaleDateString()}
                  </p>
                </>
              )}
              <p className="text-xs text-text-secondary">
                {family.version_count} version(s) total
              </p>
            </li>
          ))}
        </ul>
      </Card>

      <RequireRole allowedRoles={ADMIN_ROLES}>
        <ModelAdminPanel />
      </RequireRole>
    </div>
  );
}
