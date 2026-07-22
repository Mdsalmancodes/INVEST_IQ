/**
 * TanStack Query hooks for transactions, holdings, and the portfolio
 * summary — all scoped to a single portfolioId. AddTransaction's mutation
 * invalidates holdings/summary/transactions together since a single
 * transaction affects all three views simultaneously (Document 3 §3.4's
 * aggregate consistency — this is the client-side reflection of that).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { type AddTransactionPayload, type ListTransactionsParams, portfolioApi } from "../../../lib/portfolio-api";
import { portfolioKeys } from "./usePortfolios";

export const transactionKeys = {
  list: (portfolioId: string, params: ListTransactionsParams) =>
    ["portfolios", portfolioId, "transactions", params] as const,
};

export const holdingKeys = {
  list: (portfolioId: string) => ["portfolios", portfolioId, "holdings"] as const,
};

export const summaryKeys = {
  detail: (portfolioId: string) => ["portfolios", portfolioId, "summary"] as const,
};

export function useTransactions(portfolioId: string | undefined, params: ListTransactionsParams = {}) {
  return useQuery({
    queryKey: transactionKeys.list(portfolioId ?? "", params),
    queryFn: () => portfolioApi.listTransactions(portfolioId as string, params),
    enabled: portfolioId !== undefined,
  });
}

export function useHoldings(portfolioId: string | undefined) {
  return useQuery({
    queryKey: holdingKeys.list(portfolioId ?? ""),
    queryFn: () => portfolioApi.getHoldings(portfolioId as string),
    enabled: portfolioId !== undefined,
  });
}

export function usePortfolioSummary(portfolioId: string | undefined) {
  return useQuery({
    queryKey: summaryKeys.detail(portfolioId ?? ""),
    queryFn: () => portfolioApi.getSummary(portfolioId as string),
    enabled: portfolioId !== undefined,
  });
}

export function useAddTransaction(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AddTransactionPayload) =>
      portfolioApi.addTransaction(portfolioId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolios", portfolioId, "transactions"] });
      queryClient.invalidateQueries({ queryKey: holdingKeys.list(portfolioId) });
      queryClient.invalidateQueries({ queryKey: summaryKeys.detail(portfolioId) });
      queryClient.invalidateQueries({ queryKey: portfolioKeys.detail(portfolioId) });
    },
  });
}
