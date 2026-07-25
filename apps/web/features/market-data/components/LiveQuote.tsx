"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Card } from "@investiq/ui";
import { useEffect } from "react";

import { marketDataKeys } from "../hooks/useMarketData";
import { useCurrentPrice } from "../hooks/useMarketData";
import { AnimatedNumber } from "../../realtime/components/AnimatedNumber";
import { useRealtimeConnection } from "../../realtime/hooks/useRealtimeConnection";
import type { CurrentPriceResponse } from "../../../lib/market-data-api";

export interface LiveQuoteProps {
  symbol: string;
}

function formatMoney(value: string): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    Number.parseFloat(value)
  );
}

function gainColorClass(price: string, previousClose: string | null): string {
  if (previousClose === null) return "text-text-primary";
  const delta = Number.parseFloat(price) - Number.parseFloat(previousClose);
  if (delta > 0) return "text-success";
  if (delta < 0) return "text-danger";
  return "text-text-primary";
}

/**
 * LiveQuote — the current-price ticker. Initial load + fallback polling
 * via useCurrentPrice's existing 30s refetchInterval (Phase 4/5,
 * UNMODIFIED — this component works identically with the WebSocket
 * entirely offline, just without the added instant updates below).
 *
 * Phase 9 ADDITIVE ENHANCEMENT: subscribes to `quote:{symbol}` over the
 * shared WebSocket connection (useRealtimeConnection, Task 11) and
 * patches the SAME TanStack Query cache entry useCurrentPrice reads from
 * (marketDataKeys.quote(symbol)) whenever a fresh tick arrives —
 * MarketDataStreamingService's own quote_channel payload shape
 * (apps/core-api/src/infrastructure/realtime/market_data_streaming_service.py's
 * _tick_to_payload) is deliberately a superset of CurrentPriceResponse's
 * fields, so this is a compatible in-place cache patch, not a shape
 * mismatch. This keeps TanStack Query the single source of truth other
 * consumers of this same query key also read from, rather than
 * introducing a second, parallel piece of local state.
 *
 * The price display uses AnimatedNumber (Task 12's animation primitive)
 * so a live tick transitions smoothly rather than snapping instantly.
 */
export function LiveQuote({ symbol }: LiveQuoteProps) {
  const { data, isLoading, isError, error } = useCurrentPrice(symbol);
  const queryClient = useQueryClient();
  const { subscribe } = useRealtimeConnection();

  useEffect(() => {
    return subscribe(`quote:${symbol}`, (envelope) => {
      const tick = envelope.data as
        | { symbol: string; price: string; previous_close: string | null; is_stale_fallback: boolean }
        | undefined;
      if (!tick) return;

      queryClient.setQueryData<CurrentPriceResponse>(marketDataKeys.quote(symbol), (previous) => ({
        symbol: tick.symbol,
        price: tick.price,
        previous_close: tick.previous_close,
        source: previous?.source ?? "realtime",
        is_stale_fallback: tick.is_stale_fallback,
      }));
    });
  }, [symbol, subscribe, queryClient]);

  if (isLoading) {
    return (
      <Card
        role="status"
        aria-live="polite"
        className="flex h-20 items-center justify-center animate-pulse bg-primary-50"
      >
        <span className="sr-only">Loading quote…</span>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
        Failed to load quote{error instanceof Error ? `: ${error.message}` : "."}
      </Card>
    );
  }

  if (!data) return null;

  const priceValue = Number.parseFloat(data.price);

  return (
    <Card className="flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-text-secondary">{data.symbol}</p>
        <AnimatedNumber
          value={priceValue}
          format={(n) => formatMoney(n.toString())}
          className={`text-2xl font-semibold ${gainColorClass(data.price, data.previous_close)}`}
        />
      </div>
      <div className="text-right text-sm text-text-secondary">
        {data.previous_close && (
          <p>Prev. close: {formatMoney(data.previous_close)}</p>
        )}
        <p>
          Source: {data.source}
          {data.is_stale_fallback && " (delayed)"}
        </p>
      </div>
    </Card>
  );
}
