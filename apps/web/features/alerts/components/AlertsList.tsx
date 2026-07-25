"use client";

import { Card } from "@investiq/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { useRealtimeConnection } from "../../realtime/hooks/useRealtimeConnection";
import { alertKeys, useAlerts, useDeleteAlert, useUpdateAlert } from "../hooks/useAlerts";

const CONDITION_LABELS: Record<string, string> = {
  price_above: "Price above",
  price_below: "Price below",
  pct_change: "% change exceeds",
  rsi_threshold: "RSI crosses",
};

export interface AlertsListProps {
  onEditAlert?: (alertId: string) => void;
}

/**
 * AlertsList — the table view of a user's alerts on the dashboard.
 * Mirrors WatchlistCards's loading/error/empty-state pattern exactly.
 *
 * Phase 9 ADDITIVE ENHANCEMENT: subscribes to the `alert` topic over the
 * shared WebSocket connection (the same push NotificationsList already
 * reacts to for its toast) and invalidates this list's own cache on
 * every trigger — a non-recurring alert's is_active flips to false the
 * moment it fires (Alert.trigger(), Phase 6), so this keeps the
 * Active/Inactive badge shown here in sync instantly rather than
 * waiting for a manual refresh. Invalidation (not a cache patch) is
 * used because the WS payload doesn't carry the full alert list shape
 * this query renders (symbol/condition_type/threshold/is_active) — only
 * the triggering Notification's own title/body/metadata.
 */
export function AlertsList({ onEditAlert }: AlertsListProps) {
  const { data, isLoading, isError, error } = useAlerts();
  const deleteAlert = useDeleteAlert();
  const queryClient = useQueryClient();
  const { subscribe } = useRealtimeConnection();

  useEffect(() => {
    return subscribe("alert", () => {
      queryClient.invalidateQueries({ queryKey: alertKeys.all });
    });
  }, [subscribe, queryClient]);

  if (isLoading) {
    return (
      <Card role="status" aria-live="polite" className="h-32 animate-pulse bg-primary-50">
        <span className="sr-only">Loading alerts…</span>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
        Failed to load alerts{error instanceof Error ? `: ${error.message}` : "."}
      </Card>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <Card className="text-sm text-text-secondary">
        You don&apos;t have any alerts yet. Create one to get notified on price moves.
      </Card>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-primary-100">
      <table className="w-full text-left text-sm">
        <thead className="bg-primary-50 text-text-secondary">
          <tr>
            <th className="px-4 py-2">Symbol</th>
            <th className="px-4 py-2">Condition</th>
            <th className="px-4 py-2">Threshold</th>
            <th className="px-4 py-2">Status</th>
            <th className="px-4 py-2" />
          </tr>
        </thead>
        <tbody>
          {data.items.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              onEdit={onEditAlert}
              onDelete={(alertId) => deleteAlert.mutate(alertId)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AlertRow({
  alert,
  onEdit,
  onDelete,
}: {
  alert: {
    id: string;
    symbol: string | null;
    condition_type: string;
    threshold: string;
    is_active: boolean;
  };
  onEdit?: (alertId: string) => void;
  onDelete: (alertId: string) => void;
}) {
  const updateAlert = useUpdateAlert(alert.id);

  return (
    <tr className="border-t border-primary-100">
      <td className="px-4 py-2 font-medium text-text-primary">{alert.symbol ?? "—"}</td>
      <td className="px-4 py-2 text-text-secondary">
        {CONDITION_LABELS[alert.condition_type] ?? alert.condition_type}
      </td>
      <td className="px-4 py-2 text-text-secondary">{alert.threshold}</td>
      <td className="px-4 py-2">
        <button
          type="button"
          onClick={() => updateAlert.mutate({ is_active: !alert.is_active })}
          className={
            alert.is_active
              ? "rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success"
              : "rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-text-secondary"
          }
        >
          {alert.is_active ? "Active" : "Inactive"}
        </button>
      </td>
      <td className="px-4 py-2 text-right">
        {onEdit && (
          <button
            type="button"
            onClick={() => onEdit(alert.id)}
            className="mr-3 text-sm text-primary hover:underline"
          >
            Edit
          </button>
        )}
        <button
          type="button"
          onClick={() => onDelete(alert.id)}
          className="text-sm text-danger hover:underline"
        >
          Delete
        </button>
      </td>
    </tr>
  );
}
