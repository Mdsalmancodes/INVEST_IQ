/**
 * Typed API client for alert endpoints — follows lib/watchlist-api.ts's
 * authorizedRequest<T>() pattern. All 5 alert endpoints require a bearer
 * access token — alerts are private per-user resources, matching
 * Watchlist's contrast with Market Data's public design.
 */

import { useAuthStore } from "../store/auth-store";
import { ApiError, type ApiErrorPayload } from "./auth-api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

async function authorizedRequest<TResponse>(
  path: string,
  options: RequestInit = {}
): Promise<TResponse> {
  const accessToken = useAuthStore.getState().accessToken;
  if (!accessToken) {
    throw new ApiError("NOT_AUTHENTICATED", "No active session", 401);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...options.headers,
    },
  });

  if (response.status === 204) {
    return undefined as TResponse;
  }

  const body = await response.json();

  if (!response.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : ((body as ApiErrorPayload)?.error?.message ?? "Request failed");
    const code = (body as ApiErrorPayload)?.error?.code ?? "REQUEST_FAILED";
    throw new ApiError(code, detail, response.status);
  }

  return body as TResponse;
}

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

function buildQueryString(
  params: Record<string, string | number | boolean | undefined>
): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    searchParams.append(key, String(value));
  }
  const query = searchParams.toString();
  return query ? `?${query}` : "";
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
