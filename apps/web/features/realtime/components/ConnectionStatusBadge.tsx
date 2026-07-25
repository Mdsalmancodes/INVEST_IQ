"use client";

import { useRealtimeConnection } from "../hooks/useRealtimeConnection";

/**
 * ConnectionStatusBadge — Phase 9's "connection/offline/reconnecting
 * indicators" requirement. A small always-visible badge reflecting
 * useRealtimeConnection's own connectionState. Renders nothing while
 * "connected" (the common, unremarkable case) or "offline" while simply
 * not authenticated (nothing to report — that's just the logged-out
 * state, not a connectivity problem) — only "connecting" and
 * "reconnecting" surface a visible badge, since those are the states a
 * user actually benefits from being told about (data may be stale).
 */
export function ConnectionStatusBadge() {
  const { connectionState } = useRealtimeConnection();

  if (connectionState === "connected" || connectionState === "offline") {
    return null;
  }

  const label = connectionState === "connecting" ? "Connecting…" : "Reconnecting…";

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed left-1/2 top-4 z-50 -translate-x-1/2 rounded-full border border-warning/40 bg-warning/10 px-4 py-1.5 text-sm font-medium text-text-primary shadow-sm"
    >
      <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-warning" />
      {label}
    </div>
  );
}
