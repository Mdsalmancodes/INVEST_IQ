"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { useSessionManager } from "../features/auth/hooks/useSessionManager";
import { useSilentSessionBootstrap } from "../features/auth/hooks/useSilentSessionBootstrap";
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
 * Post-launch addition: useSilentSessionBootstrap runs BEFORE
 * useSessionManager's own effects can matter — it's what actually
 * populates useAuthStore from the httpOnly refresh-token cookie on a
 * fresh page load/reload, closing the gap where the access token being
 * in-memory-only meant every reload of a /dashboard/* page looked
 * logged-out to the client even though middleware.ts's server-side
 * cookie check would have let the request through.
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
  useSilentSessionBootstrap();
  useSessionManager();
  return (
    <QueryClientProvider client={queryClient}>
      <ConnectionStatusBadge />
      <ToastContainer />
      {children}
    </QueryClientProvider>
  );
}
