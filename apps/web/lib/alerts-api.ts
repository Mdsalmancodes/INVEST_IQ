/**
 * Typed API client for alert endpoints — follows lib/watchlist-api.ts's
 * authorizedRequest<T>() pattern. All 5 alert endpoints require a bearer
 * access token — alerts are private per-user resources, matching
 * Watchlist's contrast with Market Data's public design.
 */

import { authorizedRequest, buildQueryString } from "./api-client-helpers";

export type ConditionType = "price_above" | "price_below" | "pct_change" | "rsi_threshold";

export interface AlertResponse {
  id: string;
  user_id: string;
  instrument_id: string;
  symbol: string | null;
  condition_type: ConditionType;
  threshold: string;
  is_recurring: boolean;
  cooldown_minutes: number;
  is_active: boolean;
  triggered_at: string | null;
  created_at: string;
}

export interface AlertListResponse {
  items: AlertResponse[];
  total_count: number;
  page: number;
  page_size: number;
}

export interface CreateAlertPayload {
  symbol: string;
  condition_type: ConditionType;
  threshold: string;
  is_recurring?: boolean;
  cooldown_minutes?: number;
}

export interface UpdateAlertPayload {
  condition_type?: ConditionType;
  threshold?: string;
  is_recurring?: boolean;
  cooldown_minutes?: number;
  is_active?: boolean;
}

export interface ListAlertsParams {
  isActive?: boolean;
  sortBy?: "created_at" | "threshold";
  sortDirection?: "asc" | "desc";
  page?: number;
  pageSize?: number;
}

export const alertsApi = {
  createAlert: (payload: CreateAlertPayload) =>
    authorizedRequest<AlertResponse>("/api/v1/alerts", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listAlerts: (params: ListAlertsParams = {}) =>
    authorizedRequest<AlertListResponse>(
      `/api/v1/alerts${buildQueryString({
        is_active: params.isActive,
        sort_by: params.sortBy,
        sort_direction: params.sortDirection,
        page: params.page,
        page_size: params.pageSize,
      })}`
    ),

  getAlert: (alertId: string) => authorizedRequest<AlertResponse>(`/api/v1/alerts/${alertId}`),

  updateAlert: (alertId: string, payload: UpdateAlertPayload) =>
    authorizedRequest<AlertResponse>(`/api/v1/alerts/${alertId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteAlert: (alertId: string) =>
    authorizedRequest<undefined>(`/api/v1/alerts/${alertId}`, { method: "DELETE" }),
};
