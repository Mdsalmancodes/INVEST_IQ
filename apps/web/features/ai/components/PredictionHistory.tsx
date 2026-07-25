"use client";

import { Card } from "@investiq/ui";

import { usePredictionHistory } from "../hooks/useAi";

export interface PredictionHistoryProps {
  symbol: string;
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

/**
 * PredictionHistory — the "Predictions > History" view (Document 4
 * §10.2 step 4: an immutable, never-overwritten record of past ensemble
 * predictions per symbol), including actual_price/absolute error once a
 * backfill job populates it (disclosed as unbuilt this phase in
 * known-issues.md — actual_price will show "—" until then).
 */
export function PredictionHistory({ symbol }: PredictionHistoryProps) {
  const { data, isLoading, isError, error } = usePredictionHistory(symbol);

  if (isLoading) {
    return (
      <Card
        role="status"
        aria-live="polite"
        className="flex h-32 items-center justify-center animate-pulse bg-primary-50"
      >
        <span className="sr-only">Loading prediction history…</span>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
        Failed to load prediction history{error instanceof Error ? `: ${error.message}` : "."}
      </Card>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <Card className="flex h-32 items-center justify-center text-sm text-text-secondary">
        No prediction history yet for {symbol}.
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-text-primary">Prediction History</h3>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-xs text-text-secondary">
            <th className="pb-2">Date</th>
            <th className="pb-2">Ensemble Price</th>
            <th className="pb-2">Confidence</th>
            <th className="pb-2">Actual Price</th>
            <th className="pb-2">Data Quality</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((run) => (
            <tr key={run.id} className="border-t border-primary-100">
              <td className="py-2 text-text-secondary">{formatDate(run.created_at)}</td>
              <td className="py-2 font-medium text-text-primary">
                {formatMoney(run.ensemble_price)}
              </td>
              <td className="py-2">{Math.round(run.ensemble_confidence * 100)}%</td>
              <td className="py-2 text-text-secondary">
                {run.actual_price !== null ? formatMoney(run.actual_price) : "—"}
              </td>
              <td className="py-2 text-text-secondary">{run.data_quality}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
