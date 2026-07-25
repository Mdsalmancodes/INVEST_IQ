/**
 * TanStack Query hooks for alert CRUD — follows useWatchlists.ts's
 * convention exactly. Query keys follow the ['alerts', ...] convention so
 * cache invalidation after a mutation (create/update/delete) can target
 * exactly the affected queries.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  alertsApi,
  type CreateAlertPayload,
  type ListAlertsParams,
  type UpdateAlertPayload,
} from "../../../lib/alerts-api";

export const alertKeys = {
  all: ["alerts"] as const,
  list: (params: ListAlertsParams) => ["alerts", "list", params] as const,
  detail: (alertId: string) => ["alerts", "detail", alertId] as const,
};

export function useAlerts(params: ListAlertsParams = {}) {
  return useQuery({
    queryKey: alertKeys.list(params),
    queryFn: () => alertsApi.listAlerts(params),
  });
}

export function useAlert(alertId: string | undefined) {
  return useQuery({
    queryKey: alertKeys.detail(alertId ?? ""),
    queryFn: () => alertsApi.getAlert(alertId as string),
    enabled: alertId !== undefined,
  });
}

export function useCreateAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateAlertPayload) => alertsApi.createAlert(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: alertKeys.all });
    },
  });
}

export function useUpdateAlert(alertId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UpdateAlertPayload) => alertsApi.updateAlert(alertId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: alertKeys.detail(alertId) });
      queryClient.invalidateQueries({ queryKey: alertKeys.all });
    },
  });
}

export function useDeleteAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (alertId: string) => alertsApi.deleteAlert(alertId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: alertKeys.all });
    },
  });
}
