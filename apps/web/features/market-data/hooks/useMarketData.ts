/**
 * TanStack Query hooks for market_data — public/unauthenticated, so no
 * auth-store dependency unlike features/portfolio's hooks.
 */

import { useQuery } from "@tanstack/react-query";

import { marketDataApi } from "../../../lib/market-data-api";

export const marketDataKeys = {
  quote: (symbol: string) => ["market-data", "quote", symbol] as const,
  prices: (symbol: string, params: Record<string, string | undefined>) =>
    ["market-data", "prices", symbol, params] as const,
  bars: (symbol: string, params: Record<string, string | undefined>) =>
    ["market-data", "bars", symbol, params] as const,
  corporateActions: (symbol: string) => ["market-data", "corporate-actions", symbol] as const,
  marketStatus: () => ["market-data", "status"] as const,
};

/** Live quote — short staleTime + periodic refetch, matching the
 * backend's 30s cache TTL (src/infrastructure/market_data/cache.py). */
export function useCurrentPrice(symbol: string | undefined) {
  return useQuery({
    queryKey: marketDataKeys.quote(symbol ?? ""),
    queryFn: () => marketDataApi.getCurrentPrice(symbol as string),
    enabled: symbol !== undefined && symbol.length > 0,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}

export function useHistoricalPrices(
  symbol: string | undefined,
  params: { interval?: string; start?: string; end?: string } = {}
) {
  return useQuery({
    queryKey: marketDataKeys.prices(symbol ?? "", params),
    queryFn: () => marketDataApi.getHistoricalPrices(symbol as string, params),
    enabled: symbol !== undefined && symbol.length > 0,
  });
}

export function useOhlcvBars(
  symbol: string | undefined,
  params: { interval?: string; start?: string; end?: string } = {}
) {
  return useQuery({
    queryKey: marketDataKeys.bars(symbol ?? "", params),
    queryFn: () => marketDataApi.getOhlcvBars(symbol as string, params),
    enabled: symbol !== undefined && symbol.length > 0,
  });
}

export function useCorporateActions(symbol: string | undefined) {
  return useQuery({
    queryKey: marketDataKeys.corporateActions(symbol ?? ""),
    queryFn: () => marketDataApi.getCorporateActions(symbol as string),
    enabled: symbol !== undefined && symbol.length > 0,
  });
}

export function useMarketStatus() {
  return useQuery({
    queryKey: marketDataKeys.marketStatus(),
    queryFn: () => marketDataApi.getMarketStatus(),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}

export function useInstrumentSearch(query: string) {
  return useQuery({
    queryKey: ["market-data", "search", query],
    queryFn: () => marketDataApi.searchInstruments(query),
    enabled: query.trim().length > 0,
  });
}
