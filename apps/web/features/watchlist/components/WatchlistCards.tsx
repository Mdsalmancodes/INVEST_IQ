"use client";

import { Card } from "@investiq/ui";

import { useWatchlists } from "../hooks/useWatchlists";

export interface WatchlistCardsProps {
  onSelectWatchlist: (watchlistId: string) => void;
  onEditWatchlist: (watchlistId: string) => void;
}

/**
 * WatchlistCards — the grid view of a user's watchlists on the dashboard.
 * Uses the lighter WatchlistSummaryResponse (item_count only, no live
 * quotes) matching the backend's deliberate list/detail split — see
 * watchlist_dto.py's WatchlistSummaryResponse docstring.
 */
export function WatchlistCards({ onSelectWatchlist, onEditWatchlist }: WatchlistCardsProps) {
  const { data, isLoading, isError, error } = useWatchlists();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Card
            key={i}
            role="status"
            aria-live="polite"
            className="h-32 animate-pulse bg-primary-50"
          >
            <span className="sr-only">Loading watchlists…</span>
          </Card>
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
        Failed to load watchlists{error instanceof Error ? `: ${error.message}` : "."}
      </Card>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <Card className="text-sm text-text-secondary">
        You don&apos;t have any watchlists yet. Create one to start tracking symbols.
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {data.items.map((watchlist) => (
        <Card key={watchlist.id} className="flex flex-col gap-2">
          <div className="flex items-start justify-between">
            <button
              type="button"
              onClick={() => onSelectWatchlist(watchlist.id)}
              className="text-left text-lg font-semibold text-text-primary hover:underline"
            >
              {watchlist.name}
            </button>
            {watchlist.is_default && (
              <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary">
                Default
              </span>
            )}
          </div>
          <p className="text-sm text-text-secondary">
            {watchlist.item_count} {watchlist.item_count === 1 ? "symbol" : "symbols"}
          </p>
          <button
            type="button"
            onClick={() => onEditWatchlist(watchlist.id)}
            className="mt-auto self-end text-sm text-primary hover:underline"
          >
            Edit
          </button>
        </Card>
      ))}
    </div>
  );
}
