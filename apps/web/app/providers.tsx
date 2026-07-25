"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { useSessionManager } from "../features/auth/hooks/useSessionManager";
import { ConnectionStatusBadge } from "../features/realtime/components/ConnectionStatusBadge";
import { ToastContainer } from "../features/realtime/components/Toast";
import { createQueryClient } from "../lib/query-client";

/**
 * Phase 8 addition: useSessionManager runs here so proactive token
 * refresh and idle-timeout auto-logout are active across the entire
 * app, without requiring every page to individually mount it. The hook
 * itself is a no-op whenever there's no active session (isAuthenticated
 * is false), so this has zero effect on public/unauthenticated pages.
 *
 * Phase 9 addition: ConnectionStatusBadge and ToastContainer are mounted
 * here for the same reason — every authenticated page gets the
 * connection/reconnecting indicator and toast notifications for free,
 * without each page needing to remember to include them. Both are
 * no-ops (render nothing) while logged out, matching useSessionManager's
 * own pattern.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(createQueryClient);
  useSessionManager();
  return (
    <QueryClientProvider client={queryClient}>
      <ConnectionStatusBadge />
      <ToastContainer />
      {children}
    </QueryClientProvider>
  );
}
