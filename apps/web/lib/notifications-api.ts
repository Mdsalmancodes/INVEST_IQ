/**
 * Typed API client for notification + notification-preference endpoints —
 * follows lib/alerts-api.ts's authorizedRequest<T>() pattern. All 5
 * endpoints require a bearer access token — notifications are private
 * per-user resources, matching Alerts/Watchlist's contrast with Market
 * Data's public design.
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

export type DigestFrequency = "off" | "daily" | "weekly";

export interface NotificationResponse {
  id: string;
  user_id: string;
  type: string;
  title: string;
  body: string;
  metadata: Record<string, unknown>;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationResponse[];
  total_count: number;
  unread_count: number;
  page: number;
  page_size: number;
}

export interface MarkAllAsReadResponse {
  marked_count: number;
}

export interface NotificationPreferencesResponse {
  user_id: string;
  price_alerts_email: boolean;
  price_alerts_push: boolean;
  digest_frequency: DigestFrequency;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
}

export interface UpdateNotificationPreferencesPayload {
  price_alerts_email?: boolean;
  price_alerts_push?: boolean;
  digest_frequency?: DigestFrequency;
  quiet_hours_start?: string;
  quiet_hours_end?: string;
  clear_quiet_hours?: boolean;
}

export interface ListNotificationsParams {
  unreadOnly?: boolean;
  page?: number;
  pageSize?: number;
}

function buildQueryString(params: Record<string, string | number | boolean | undefined>): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    searchParams.append(key, String(value));
  }
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export const notificationsApi = {
  listNotifications: (params: ListNotificationsParams = {}) =>
    authorizedRequest<NotificationListResponse>(
      `/api/v1/notifications${buildQueryString({
        unread_only: params.unreadOnly,
        page: params.page,
        page_size: params.pageSize,
      })}`
    ),

  markAsRead: (notificationId: string) =>
    authorizedRequest<NotificationResponse>(`/api/v1/notifications/${notificationId}/read`, {
      method: "PATCH",
    }),

  markAllAsRead: () =>
    authorizedRequest<MarkAllAsReadResponse>("/api/v1/notifications/read-all", {
      method: "POST",
    }),

  getPreferences: () =>
    authorizedRequest<NotificationPreferencesResponse>("/api/v1/notifications/preferences"),

  updatePreferences: (payload: UpdateNotificationPreferencesPayload) =>
    authorizedRequest<NotificationPreferencesResponse>("/api/v1/notifications/preferences", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};
