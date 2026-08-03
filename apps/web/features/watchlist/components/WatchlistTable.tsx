"use client";

import { Card } from "@investiq/ui";
import { watchlistTickSchema } from "@investiq/validation";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect } from "react";

import type { WatchlistResponse } from "../../../lib/watchlist-api";
import { useRealtimeConnection } from "../../realtime/hooks/useRealtimeConnection";
import { useRemoveWatchlistItem, useUpdateWatchlistItem, useWatchlist, watchlistKeys } from "../hooks/useWatchlists";

export interface WatchlistTableProps {
  watchlistId: string;
}

function formatMoney(value: string | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    Number.parseFloat(value)
  );
}

function formatPercent(value: string | null): string {
  if (value === null) return "—";
  return `${Number.parseFloat(value).toFixed(2)}%`;
}

function gainColorClass(value: string | null): string {
  if (value === null) return "text-text-secondary";
  const num = Number.parseFloat(value);
  if (num > 0) return "text-success";
  if (num < 0) return "text-danger";
  return "text-text-secondary";
}

/**
 * WatchlistTable — the per-item breakdown for a single watchlist: live
 * price, daily change/%, market status/delayed indicator, last updated
 * (via WatchlistEnrichmentService, Phase 4/5 integration point), plus
 * pin/reorder/remove actions. Uses GET /watchlists/{id} (the full detail
 * endpoint with quotes), not the list endpoint. Initial load + fallback
 * polling via useWatchlist's existing 30s refetchInterval (Phase 5,
 * UNMODIFIED — this component works identically with the WebSocket
 * entirely offline).
 *
 * Phase 9 ADDITIVE ENHANCEMENT: subscribes to `watchlist` over the
 * shared WebSocket connection and merges each incoming enriched-
 * watchlist tick (WatchlistStreamingService's own
 * _enriched_watchlist_to_payload shape — item_id-keyed quote fields
 * only) into the SAME TanStack Query cache entry useWatchlist reads
 * from, preserving every non-quote field (id/instrument_id/position/
 * is_pinned/etc.) already present on each item — the WS tick only ever
 * carries quote data, never the full item record. A tick for a
 * DIFFERENT watchlist_id than this component's own watchlistId is
 * ignored (the server pushes one message per watchlist the user has
 * open a topic subscription for; a page showing multiple watchlists
 * mounts one WatchlistTable per id, each filtering to its own).
 */
export function WatchlistTable({ watchlistId }: WatchlistTableProps) {
  const { data: watchlist, isLoading, isError, error } = useWatchlist(watchlistId);
  const updateItem = useUpdateWatchlistItem(watchlistId);
  const removeItem = useRemoveWatchlistItem(watchlistId);
  const queryClient = useQueryClient();
  const { subscribe } = useRealtimeConnection();

  useEffect(() => {
    return subscribe("watchlist", (envelope) => {
      const parsed = watchlistTickSchema.safeParse(envelope.data);
      if (!parsed.success || parsed.data.watchlist_id !== watchlistId) return;
      const tick = parsed.data;

      queryClient.setQueryData<WatchlistResponse>(
        watchlistKeys.detail(watchlistId),
        (previous) => {
          if (!previous) return previous;
          const quoteByItemId = new Map(tick.items.map((i) => [i.item_id, i]));
          return {
            ...previous,
            market_status: tick.market_status,
            items: previous.items.map((item) => {
              const freshQuote = quoteByItemId.get(item.id);
              if (!freshQuote || !item.quote) return item;
              return {
                ...item,
                quote: {
                  ...item.quote,
                  price: freshQuote.price,
                  previous_close: freshQuote.previous_close,
                  daily_change: freshQuote.daily_change,
                  daily_change_pct: freshQuote.daily_change_pct,
                  is_delayed: freshQuote.is_delayed,
                  error: freshQuote.error,
                },
              };
            }),
          };
        }
      );
    });
  }, [watchlistId, subscribe, queryClient]);

  if (isLoading) {
    return (
      <Card role="status" aria-live="polite" className="h-64 animate-pulse bg-primary-50">
        <span className="sr-only">Loading watchlist…</span>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
        Failed to load watchlist{error instanceof Error ? `: ${error.message}` : "."}
      </Card>
    );
  }

  if (!watchlist) return null;

  if (watchlist.items.length === 0) {
    return (
      <Card className="text-sm text-text-secondary">
        This watchlist is empty. Add a symbol to start tracking it.
      </Card>
    );
  }

  const sortedItems = [...watchlist.items].sort((a, b) => a.position - b.position);

  return (
    <Card className="overflow-x-auto p-0">
      {watchlist.market_status && (
        <p className="px-4 pt-4 text-sm text-text-secondary">
          Market status: <span className="font-medium text-text-primary">{watchlist.market_status}</span>
        </p>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-primary-100 text-left text-text-secondary">
            <th className="px-4 py-3 font-medium">Symbol</th>
            <th className="px-4 py-3 font-medium">Price</th>
            <th className="px-4 py-3 font-medium">Daily Change</th>
            <th className="px-4 py-3 font-medium">Daily %</th>
            <th className="px-4 py-3 font-medium">Updated</th>
            <th className="px-4 py-3 font-medium">Pinned</th>
            <th className="px-4 py-3 font-medium" />
          </tr>
        </thead>
        <tbody>
          {sortedItems.map((item) => {
            const quote = item.quote;
            return (
              <tr key={item.id} className="border-b border-primary-50 last:border-0">
                <td className="px-4 py-3 font-medium text-text-primary">
                  {item.symbol ? (
                    <Link href={`/markets/${item.symbol}`} className="hover:underline">
                      {item.symbol}
                    </Link>
                  ) : (
                    item.instrument_id
                  )}
                </td>
                <td className="px-4 py-3">
                  {quote?.error ? (
                    <span role="alert" className="text-danger">
                      {quote.error}
                    </span>
                  ) : (
                    formatMoney(quote?.price ?? null)
                  )}
                </td>
                <td className={`px-4 py-3 ${gainColorClass(quote?.daily_change ?? null)}`}>
                  {formatMoney(quote?.daily_change ?? null)}
                </td>
                <td className={`px-4 py-3 ${gainColorClass(quote?.daily_change_pct ?? null)}`}>
                  {formatPercent(quote?.daily_change_pct ?? null)}
                </td>
                <td className="px-4 py-3 text-text-secondary">
                  {quote?.is_delayed ? "Delayed" : "Live"}
                </td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    aria-pressed={item.is_pinned}
                    aria-label={item.is_pinned ? "Unpin from top" : "Pin to top"}
                    onClick={() =>
                      updateItem.mutate({
                        itemId: item.id,
                        payload: { is_pinned: !item.is_pinned },
                      })
                    }
                    className={item.is_pinned ? "text-primary" : "text-text-secondary"}
                  >
                    {item.is_pinned ? "★" : "☆"}
                  </button>
                </td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    onClick={() => removeItem.mutate(item.id)}
                    className="text-sm text-danger hover:underline"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
