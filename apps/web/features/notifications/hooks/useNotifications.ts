/**
 * TanStack Query hooks for notifications + notification preferences —
 * follows useAlerts.ts's convention exactly. Query keys follow the
 * ['notifications', ...] convention so cache invalidation after a
 * mutation (mark-as-read/mark-all-as-read/update-preferences) can target
 * exactly the affected queries.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type ListNotificationsParams,
  notificationsApi,
  type UpdateNotificationPreferencesPayload,
} from "../../../lib/notifications-api";

export const notificationKeys = {
  all: ["notifications"] as const,
  list: (params: ListNotificationsParams) => ["notifications", "list", params] as const,
  preferences: ["notifications", "preferences"] as const,
};

export function useNotifications(params: ListNotificationsParams = {}) {
  return useQuery({
    queryKey: notificationKeys.list(params),
    queryFn: () => notificationsApi.listNotifications(params),
    // Matches the unread-badge use case's need for reasonably fresh data
    // without a live/WebSocket layer (Phase 6 disclosed scope — see
    // known-issues.md), polling every 30s like Watchlist's quote refresh.
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}

export function useMarkNotificationAsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) => notificationsApi.markAsRead(notificationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.all });
    },
  });
}

export function useMarkAllNotificationsAsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => notificationsApi.markAllAsRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.all });
    },
  });
}

export function useNotificationPreferences() {
  return useQuery({
    queryKey: notificationKeys.preferences,
    queryFn: () => notificationsApi.getPreferences(),
  });
}

export function useUpdateNotificationPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UpdateNotificationPreferencesPayload) =>
      notificationsApi.updatePreferences(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.preferences });
    },
  });
}
