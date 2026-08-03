"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { WatchlistDashboard } from "../../../features/watchlist/components/WatchlistDashboard";
import { useAuthStore } from "../../../store/auth-store";

/**
 * Watchlist dashboard — Phase 5 target. Client-side auth guard matching
 * app/dashboard/portfolios/page.tsx's exact pattern (redirects to /login
 * if there's no access token in memory — the same disclosed BFF-cookie
 * limitation carried forward from Phase 2/3).
 */
export default function WatchlistsPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isBootstrapping = useAuthStore((state) => state.isBootstrapping);

  useEffect(() => {
    if (!isBootstrapping && !isAuthenticated) {
      router.replace("/login?redirectTo=%2Fdashboard%2Fwatchlists");
    }
  }, [isAuthenticated, isBootstrapping, router]);

  if (isBootstrapping || !isAuthenticated) {
    return null;
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto max-w-5xl">
        <WatchlistDashboard
          onSelectWatchlist={(watchlistId) => router.push(`/dashboard/watchlists/${watchlistId}`)}
        />
      </div>
    </main>
  );
}
