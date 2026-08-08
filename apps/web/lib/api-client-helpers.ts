/**
 * Shared HTTP-client helpers extracted from the identical `authorizedRequest`/
 * `buildQueryString` implementations that were previously duplicated
 * verbatim across lib/portfolio-api.ts, lib/ai-api.ts, lib/watchlist-api.ts,
 * lib/alerts-api.ts, and lib/notifications-api.ts (with lib/market-data-api.ts
 * duplicating an unauthenticated variant, `publicRequest`, plus its own
 * `buildQueryString`). Consolidated here per the production audit's dead-
 * code/duplication finding — behavior is preserved exactly: same bearer-
 * token read from useAuthStore, same 204-as-undefined short-circuit, same
 * dual error-shape handling (FastAPI's plain `{detail}` vs. this backend's
 * structured `{success:false,error:{code,message}}`), same query-string
 * building (now a single implementation that is a strict superset of every
 * prior call site's param-value union: string | number | boolean | string[]).
 */

import { useAuthStore } from "../store/auth-store";
import { ApiError, type ApiErrorPayload } from "./auth-api";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function parseErrorAndThrow(response: Response): Promise<never> {
  const body = await response.json();
  const detail =
    typeof body?.detail === "string"
      ? body.detail
      : ((body as ApiErrorPayload)?.error?.message ?? "Request failed");
  const code = (body as ApiErrorPayload)?.error?.code ?? "REQUEST_FAILED";
  throw new ApiError(code, detail, response.status);
}

/**
 * For endpoints that require a bearer access token (every private,
 * per-user resource — portfolios, watchlists, alerts, notifications, AI).
 */
export async function authorizedRequest<TResponse>(
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

  if (!response.ok) {
    return parseErrorAndThrow(response);
  }

  return (await response.json()) as TResponse;
}

/**
 * For endpoints that are public reference data and never require
 * authentication (market data only, per its backend router's disclosed
 * design decision).
 */
export async function publicRequest<TResponse>(path: string): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
  });

  if (!response.ok) {
    return parseErrorAndThrow(response);
  }

  return (await response.json()) as TResponse;
}

/**
 * Builds a `?key=value&...` query string, skipping undefined values and
 * expanding array values into repeated `key=item` params (matching
 * lib/portfolio-api.ts's prior array-handling behavior for e.g.
 * transaction `type` filters) — a strict superset of every prior
 * per-file buildQueryString's narrower param-value union.
 */
export function buildQueryString(
  params: Record<string, string | number | boolean | string[] | undefined>
): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) {
      for (const item of value) searchParams.append(key, item);
    } else {
      searchParams.append(key, String(value));
    }
  }
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}
