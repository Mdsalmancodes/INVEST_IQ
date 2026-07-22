"use client";

import { Button } from "@investiq/ui";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AddSymbolDialog } from "../../../../features/watchlist/components/AddSymbolDialog";
import { WatchlistTable } from "../../../../features/watchlist/components/WatchlistTable";
import { useWatchlist } from "../../../../features/watchlist/hooks/useWatchlists";
import { useAuthStore } from "../../../../store/auth-store";

/**
 * Watchlist detail dashboard — wires together WatchlistTable and
 * AddSymbolDialog for a single watchlist, following
 * app/dashboard/portfolios/[id]/page.tsx's exact composition pattern.
 */
export default function WatchlistDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const watchlistId = params.id;
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const { data: watchlist, isLoading, isError, error } = useWatchlist(watchlistId);
  const [isAddSymbolOpen, setIsAddSymbolOpen] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace(`/login?redirectTo=%2Fdashboard%2Fwatchlists%2F${watchlistId}`);
    }
  }, [isAuthenticated, router, watchlistId]);

  if (!isAuthenticated) {
    return null;
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto max-w-5xl">
        <div className="flex items-center justify-between">
          <div>
            <Link href="/dashboard/watchlists" className="text-sm text-primary">
              ← Back to watchlists
            </Link>
            {isLoading && <p className="mt-1 text-2xl font-semibold text-text-primary">Loading…</p>}
            {isError && (
              <p role="alert" className="mt-1 text-danger">
                Failed to load watchlist{error instanceof Error ? `: ${error.message}` : "."}
              </p>
            )}
            {watchlist && (
              <h1 className="mt-1 text-2xl font-semibold text-text-primary">{watchlist.name}</h1>
            )}
          </div>
          <Button onClick={() => setIsAddSymbolOpen(true)}>Add Symbol</Button>
        </div>

        <div className="mt-6">
          <WatchlistTable watchlistId={watchlistId} />
        </div>
      </div>

      <AddSymbolDialog
        watchlistId={watchlistId}
        isOpen={isAddSymbolOpen}
        onClose={() => setIsAddSymbolOpen(false)}
      />
    </main>
  );
}
