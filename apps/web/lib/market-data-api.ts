/**
 * Typed API client for market_data endpoints — follows lib/portfolio-api.ts's
 * pattern, but UNAUTHENTICATED (no bearer token) since these endpoints are
 * public reference data per the backend's disclosed design decision
 * (src/presentation/routers/market_data_router.py's module docstring).
 */

import { buildQueryString, publicRequest } from "./api-client-helpers";

export interface CurrentPriceResponse {
  symbol: string;
  price: string;
  previous_close: string | null;
  source: string;
  is_stale_fallback: boolean;
}

export interface PricePointResponse {
  as_of: string;
  price: string;
}

export interface HistoricalPricesResponse {
  symbol: string;
  interval: string;
  points: PricePointResponse[];
  data_completeness: string;
}

export interface OhlcvBarResponse {
  bar_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  adjusted_close: string;
  volume: number;
  is_closed: boolean;
  source: string;
}

export interface OhlcvBarsResponse {
  symbol: string;
  interval: string;
  bars: OhlcvBarResponse[];
  data_completeness: string;
}

export interface CorporateActionResponse {
  id: string;
  action_type: string;
  ratio: string | null;
  cash_amount: string | null;
  ex_date: string;
  announced_at: string | null;
}

export interface CorporateActionListResponse {
  items: CorporateActionResponse[];
}

export interface MarketStatusResponse {
  is_open: boolean;
  session: string;
  as_of: string;
  next_open: string | null;
}

export interface InstrumentSearchResult {
  id: string;
  symbol: string;
  exchange: string;
  name: string;
  asset_type: string;
  currency: string;
}

export interface InstrumentSearchResponse {
  items: InstrumentSearchResult[];
}

export const marketDataApi = {
  getCurrentPrice: (symbol: string) =>
    publicRequest<CurrentPriceResponse>(`/api/v1/instruments/${symbol}/quote`),

  getHistoricalPrices: (
    symbol: string,
    params: { interval?: string; start?: string; end?: string } = {}
  ) =>
    publicRequest<HistoricalPricesResponse>(
      `/api/v1/instruments/${symbol}/prices${buildQueryString(params)}`
    ),

  getOhlcvBars: (symbol: string, params: { interval?: string; start?: string; end?: string } = {}) =>
    publicRequest<OhlcvBarsResponse>(
      `/api/v1/instruments/${symbol}/bars${buildQueryString(params)}`
    ),

  getCorporateActions: (symbol: string) =>
    publicRequest<CorporateActionListResponse>(
      `/api/v1/instruments/${symbol}/corporate-actions`
    ),

  getMarketStatus: () => publicRequest<MarketStatusResponse>("/api/v1/market/status"),

  searchInstruments: (query: string, limit = 20) =>
    publicRequest<InstrumentSearchResponse>(
      `/api/v1/instruments/search${buildQueryString({ q: query, limit: String(limit) })}`
    ),
};
