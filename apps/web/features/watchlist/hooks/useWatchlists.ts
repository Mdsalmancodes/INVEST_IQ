/**
 * TanStack Query hooks for watchlist CRUD + items — follows
 * usePortfolios.ts's convention exactly. Query keys follow the
 * ['watchlists', ...] convention so cache invalidation after a mutation
 * (create/update/delete/add-item/remove-item/update-item) can target
 * exactly the affected queries.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type AddWatchlistItemPayload,
  type CreateWatchlistPayload,
  type ListWatchlistsParams,
  type UpdateWatchlistItemPayload,
  type UpdateWatchlistPayload,
  watchlistApi,
} from "../../../lib/watchlist-api";

export const watchlistKeys = {
  all: ["watchlists"] as const,
  list: (params: ListWatchlistsParams) => ["watchlists", "list", params] as const,
  detail: (watchlistId: string) => ["watchlists", "detail", watchlistId] as const,
};

export function useWatchlists(params: ListWatchlistsParams = {}) {
  return useQuery({
    queryKey: watchlistKeys.list(params),
    queryFn: () => watchlistApi.listWatchlists(params),
  });
}

export function useWatchlist(watchlistId: string | undefined) {
  return useQuery({
    queryKey: watchlistKeys.detail(watchlistId ?? ""),
    queryFn: () => watchlistApi.getWatchlist(watchlistId as string),
    enabled: watchlistId !== undefined,
    // Matches the 30s quote-cache TTL backing this endpoint's enrichment
    // (WatchlistEnrichmentService -> GetCurrentPriceUseCase's MarketDataCache),
    // so refetching doesn't outrun how often the underlying quotes change.
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}

export function useCreateWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateWatchlistPayload) => watchlistApi.createWatchlist(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.all });
    },
  });
}

export function useUpdateWatchlist(watchlistId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UpdateWatchlistPayload) =>
      watchlistApi.updateWatchlist(watchlistId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(watchlistId) });
      queryClient.invalidateQueries({ queryKey: watchlistKeys.all });
    },
  });
}

export function useDeleteWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (watchlistId: string) => watchlistApi.deleteWatchlist(watchlistId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.all });
    },
  });
}

export function useAddWatchlistItem(watchlistId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AddWatchlistItemPayload) => watchlistApi.addItem(watchlistId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(watchlistId) });
      queryClient.invalidateQueries({ queryKey: watchlistKeys.all });
    },
  });
}

export function useRemoveWatchlistItem(watchlistId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => watchlistApi.removeItem(watchlistId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(watchlistId) });
      queryClient.invalidateQueries({ queryKey: watchlistKeys.all });
    },
  });
}

export function useUpdateWatchlistItem(watchlistId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      itemId,
      payload,
    }: {
      itemId: string;
      payload: UpdateWatchlistItemPayload;
    }) => watchlistApi.updateItem(watchlistId, itemId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(watchlistId) });
    },
  });
}
