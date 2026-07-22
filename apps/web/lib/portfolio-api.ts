/**
 * Typed API client for portfolio endpoints — follows lib/auth-api.ts's
 * request<T>() pattern (Document 2 §5.2). Unlike auth, portfolio endpoints
 * always require a bearer access token, obtained from useAuthStore
 * (Document 3 §7.5 — every portfolio_id path is scoped server-side by the
 * authenticated user, this client never needs to pass a user id).
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

export interface PortfolioResponse {
  id: string;
  user_id: string;
  name: string;
  base_currency: string;
  is_paper: boolean;
  created_at: string;
  updated_at: string;
}

export interface PortfolioListResponse {
  items: PortfolioResponse[];
  total_count: number;
  page: number;
  page_size: number;
}

export interface TransactionResponse {
  id: string;
  portfolio_id: string;
  instrument_id: string | null;
  type: string;
  quantity: string | null;
  price: string | null;
  fees: string;
  split_ratio: number | null;
  related_portfolio_id: string | null;
  cash_amount: string | null;
  executed_at: string;
  created_at: string;
  realized_gain?: string | null;
}

export interface TransactionListResponse {
  items: TransactionResponse[];
  total_count: number;
  page: number;
  page_size: number;
}

export interface HoldingResponse {
  id: string;
  instrument_id: string;
  quantity: string;
  average_cost: string;
}

export interface HoldingListResponse {
  items: HoldingResponse[];
}

export interface HoldingSummaryResponse {
  instrument_id: string;
  quantity: string;
  average_buy_price: string;
  current_price: string | null;
  market_value: string | null;
  unrealized_gain: string | null;
  allocation_pct: string | null;
  daily_gain: string | null;
}

export interface PortfolioSummaryResponse {
  portfolio_id: string;
  total_investment: string;
  current_value: string;
  profit_loss: string;
  profit_loss_pct: string;
  realized_gain: string;
  unrealized_gain: string;
  dividend_income: string;
  daily_gain: string;
  holdings: HoldingSummaryResponse[];
  holdings_missing_price: string[];
}

export interface CreatePortfolioPayload {
  name: string;
  base_currency: string;
  is_paper: boolean;
}

export interface UpdatePortfolioPayload {
  name?: string;
  base_currency?: string;
}

export interface AddTransactionPayload {
  type: string;
  executed_at: string;
  instrument_id?: string;
  quantity?: string;
  price?: string;
  fees?: string;
  split_ratio?: number;
  related_portfolio_id?: string;
  cash_amount?: string;
}

export interface ListTransactionsParams {
  page?: number;
  pageSize?: number;
  instrumentId?: string;
  types?: string[];
  executedAfter?: string;
  executedBefore?: string;
}

function buildQueryString(params: Record<string, string | number | string[] | undefined>): string {
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

export const portfolioApi = {
  createPortfolio: (payload: CreatePortfolioPayload) =>
    authorizedRequest<PortfolioResponse>("/api/v1/portfolios", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listPortfolios: (params: { isPaper?: boolean; page?: number; pageSize?: number } = {}) =>
    authorizedRequest<PortfolioListResponse>(
      `/api/v1/portfolios${buildQueryString({
        is_paper: params.isPaper !== undefined ? String(params.isPaper) : undefined,
        page: params.page,
        page_size: params.pageSize,
      })}`
    ),

  getPortfolio: (portfolioId: string) =>
    authorizedRequest<PortfolioResponse>(`/api/v1/portfolios/${portfolioId}`),

  updatePortfolio: (portfolioId: string, payload: UpdatePortfolioPayload) =>
    authorizedRequest<PortfolioResponse>(`/api/v1/portfolios/${portfolioId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deletePortfolio: (portfolioId: string) =>
    authorizedRequest<undefined>(`/api/v1/portfolios/${portfolioId}`, { method: "DELETE" }),

  addTransaction: (portfolioId: string, payload: AddTransactionPayload) =>
    authorizedRequest<TransactionResponse>(`/api/v1/portfolios/${portfolioId}/transactions`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listTransactions: (portfolioId: string, params: ListTransactionsParams = {}) =>
    authorizedRequest<TransactionListResponse>(
      `/api/v1/portfolios/${portfolioId}/transactions${buildQueryString({
        page: params.page,
        page_size: params.pageSize,
        instrument_id: params.instrumentId,
        type: params.types,
        executed_after: params.executedAfter,
        executed_before: params.executedBefore,
      })}`
    ),

  getHoldings: (portfolioId: string) =>
    authorizedRequest<HoldingListResponse>(`/api/v1/portfolios/${portfolioId}/holdings`),

  getSummary: (portfolioId: string) =>
    authorizedRequest<PortfolioSummaryResponse>(`/api/v1/portfolios/${portfolioId}/summary`),
};
