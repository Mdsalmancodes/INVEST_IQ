/**
 * TanStack Query hooks for the portfolio list/CRUD endpoints — Document 2
 * §6.2: "React Query owns all server state." Query keys follow the
 * ['portfolios', ...] convention so cache invalidation after a mutation
 * (create/update/delete) can target exactly the affected queries.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type CreatePortfolioPayload,
  type UpdatePortfolioPayload,
  portfolioApi,
} from "../../../lib/portfolio-api";

export const portfolioKeys = {
  all: ["portfolios"] as const,
  list: (isPaper?: boolean) => ["portfolios", "list", { isPaper }] as const,
  detail: (portfolioId: string) => ["portfolios", "detail", portfolioId] as const,
};

export function usePortfolios(params: { isPaper?: boolean } = {}) {
  return useQuery({
    queryKey: portfolioKeys.list(params.isPaper),
    queryFn: () => portfolioApi.listPortfolios(params),
  });
}

export function usePortfolio(portfolioId: string | undefined) {
  return useQuery({
    queryKey: portfolioKeys.detail(portfolioId ?? ""),
    queryFn: () => portfolioApi.getPortfolio(portfolioId as string),
    enabled: portfolioId !== undefined,
  });
}

export function useCreatePortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreatePortfolioPayload) => portfolioApi.createPortfolio(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portfolioKeys.all });
    },
  });
}

export function useUpdatePortfolio(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UpdatePortfolioPayload) =>
      portfolioApi.updatePortfolio(portfolioId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portfolioKeys.detail(portfolioId) });
      queryClient.invalidateQueries({ queryKey: portfolioKeys.all });
    },
  });
}

export function useDeletePortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (portfolioId: string) => portfolioApi.deletePortfolio(portfolioId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portfolioKeys.all });
    },
  });
}
