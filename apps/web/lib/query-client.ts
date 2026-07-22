import { QueryClient } from "@tanstack/react-query";

/**
 * React Query client — Document 2 §6.2: "React Query owns all server
 * state." Default staleTime is conservative (0 = always refetch on
 * mount) since Phase 2 has no long-lived server-state queries yet (the
 * auth mutations below don't need caching); later phases tune staleTime
 * per data type as real server-state queries (portfolio, quotes, etc.)
 * are added.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}
