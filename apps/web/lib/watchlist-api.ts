/**
 * Typed API client for watchlist endpoints — follows lib/portfolio-api.ts's
 * authorizedRequest<T>() pattern. All 8 watchlist endpoints require a
 * bearer access token (unlike lib/market-data-api.ts's public design —
 * watchlists are private per-user resources, confirmed via the backend's
 * live smoke test in Phase 5 task 6/10: every endpoint returns 401 without
 * a token).
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

export interface WatchlistItemQuoteResponse {
  price: string | null;
  previous_close: string | null;
  daily_change: string | null;
  daily_change_pct: string | null;
  source: string | null;
  is_delayed: boolean;
  last_updated: string | null;
  error: string | null;
}

export interface WatchlistItemResponse {
  id: string;
  instrument_id: string;
  symbol: string | null;
  position: number;
  is_pinned: boolean;
  added_at: string;
  quote: WatchlistItemQuoteResponse | null;
}

export interface WatchlistResponse {
  id: string;
  user_id: string;
  name: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
  items: WatchlistItemResponse[];
  market_status: string | null;
}

export interface WatchlistSummaryResponse {
  id: string;
  user_id: string;
  name: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
  item_count: number;
}

export interface WatchlistListResponse {
  items: WatchlistSummaryResponse[];
  total_count: number;
  page: number;
  page_size: number;
}

export interface CreateWatchlistPayload {
  name: string;
  is_default?: boolean;
}

export interface UpdateWatchlistPayload {
  name?: string;
  is_default?: boolean;
}

export interface AddWatchlistItemPayload {
  symbol: string;
}

export interface UpdateWatchlistItemPayload {
  is_pinned?: boolean;
  position?: number;
}

export interface ListWatchlistsParams {
  search?: string;
  sortBy?: "name" | "created_at" | "updated_at";
  sortDirection?: "asc" | "desc";
  page?: number;
  pageSize?: number;
}

function buildQueryString(params: Record<string, string | number | undefined>): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    searchParams.append(key, String(value));
  }
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export const watchlistApi = {
  createWatchlist: (payload: CreateWatchlistPayload) =>
    authorizedRequest<WatchlistSummaryResponse>("/api/v1/watchlists", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listWatchlists: (params: ListWatchlistsParams = {}) =>
    authorizedRequest<WatchlistListResponse>(
      `/api/v1/watchlists${buildQueryString({
        search: params.search,
        sort_by: params.sortBy,
        sort_direction: params.sortDirection,
        page: params.page,
        page_size: params.pageSize,
      })}`
    ),

  getWatchlist: (watchlistId: string) =>
    authorizedRequest<WatchlistResponse>(`/api/v1/watchlists/${watchlistId}`),

  updateWatchlist: (watchlistId: string, payload: UpdateWatchlistPayload) =>
    authorizedRequest<WatchlistSummaryResponse>(`/api/v1/watchlists/${watchlistId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteWatchlist: (watchlistId: string) =>
    authorizedRequest<undefined>(`/api/v1/watchlists/${watchlistId}`, { method: "DELETE" }),

  addItem: (watchlistId: string, payload: AddWatchlistItemPayload) =>
    authorizedRequest<WatchlistItemResponse>(`/api/v1/watchlists/${watchlistId}/items`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateItem: (watchlistId: string, itemId: string, payload: UpdateWatchlistItemPayload) =>
    authorizedRequest<WatchlistItemResponse>(
      `/api/v1/watchlists/${watchlistId}/items/${itemId}`,
      { method: "PATCH", body: JSON.stringify(payload) }
    ),

  removeItem: (watchlistId: string, itemId: string) =>
    authorizedRequest<undefined>(`/api/v1/watchlists/${watchlistId}/items/${itemId}`, {
      method: "DELETE",
    }),
};
