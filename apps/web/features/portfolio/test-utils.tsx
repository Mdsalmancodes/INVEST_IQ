import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";

/**
 * Test helper — wraps a component under test in a fresh QueryClientProvider
 * per render, matching the real app/providers.tsx setup but with retries
 * disabled so failed-request tests don't hang waiting for retry backoff.
 */
export function renderWithQueryClient(ui: ReactElement): RenderResult {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}
