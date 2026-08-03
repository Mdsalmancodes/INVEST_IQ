"use client";

import { Card } from "@investiq/ui";
import { alertNotificationTickSchema } from "@investiq/validation";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { showToast } from "../../realtime/components/Toast";
import { useRealtimeConnection } from "../../realtime/hooks/useRealtimeConnection";
import {
  notificationKeys,
  useMarkAllNotificationsAsRead,
  useMarkNotificationAsRead,
  useNotifications,
} from "../hooks/useNotifications";

/**
 * NotificationsList — the list view of a user's notifications on the
 * dashboard. Mirrors AlertsList/WatchlistCards's loading/error/empty-state
 * pattern exactly. Initial load + fallback polling via useNotifications'
 * existing 30s refetchInterval (Phase 6, UNMODIFIED) — this component
 * works identically with the WebSocket entirely offline.
 *
 * Phase 9 ADDITIVE ENHANCEMENT: subscribes to the `alert` topic over the
 * shared WebSocket connection (AlertEvaluationStreamingService's own
 * push, Task 8 — this closes useNotifications.ts's own disclosed Phase 6
 * known-issue: "no live/WebSocket layer" is no longer true). On each
 * alert-triggered push: (1) shows an instant toast notification (the
 * "push notification the moment ... conditions are met" requirement —
 * this is the one place in the whole dashboard where a toast fires from
 * a WebSocket event rather than a user action), and (2) invalidates the
 * notifications query so the list itself refetches and shows the new
 * row — invalidation (not an optimistic cache patch) is used here
 * because the WS payload only carries the single new notification, not
 * the full paginated list/unread_count this query actually renders.
 */
export function NotificationsList() {
  const { data, isLoading, isError, error } = useNotifications();
  const markAsRead = useMarkNotificationAsRead();
  const markAllAsRead = useMarkAllNotificationsAsRead();
  const queryClient = useQueryClient();
  const { subscribe } = useRealtimeConnection();

  useEffect(() => {
    return subscribe("alert", (envelope) => {
      const parsed = alertNotificationTickSchema.safeParse(envelope.data);
      if (!parsed.success) return;
      const notification = parsed.data;

      showToast({ title: notification.title, description: notification.body, variant: "warning" });
      queryClient.invalidateQueries({ queryKey: notificationKeys.all });
    });
  }, [subscribe, queryClient]);

  if (isLoading) {
    return (
      <Card role="status" aria-live="polite" className="h-32 animate-pulse bg-primary-50">
        <span className="sr-only">Loading notifications…</span>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
        Failed to load notifications{error instanceof Error ? `: ${error.message}` : "."}
      </Card>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <Card className="text-sm text-text-secondary">
        You don&apos;t have any notifications yet.
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-secondary">
          {data.unread_count} unread {data.unread_count === 1 ? "notification" : "notifications"}
        </p>
        {data.unread_count > 0 && (
          <button
            type="button"
            onClick={() => markAllAsRead.mutate()}
            className="text-sm text-primary hover:underline"
          >
            Mark all as read
          </button>
        )}
      </div>

      <ul className="flex flex-col gap-2">
        {data.items.map((notification) => (
          <li key={notification.id}>
            <Card
              className={
                notification.is_read
                  ? "flex items-start justify-between gap-3 opacity-70"
                  : "flex items-start justify-between gap-3 border-primary/40"
              }
            >
              <div>
                <p className="font-medium text-text-primary">{notification.title}</p>
                <p className="text-sm text-text-secondary">{notification.body}</p>
              </div>
              {!notification.is_read && (
                <button
                  type="button"
                  onClick={() => markAsRead.mutate(notification.id)}
                  className="shrink-0 text-sm text-primary hover:underline"
                >
                  Mark as read
                </button>
              )}
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
