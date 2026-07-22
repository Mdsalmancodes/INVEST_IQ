"use client";

import { Card } from "@investiq/ui";

import { useCurrentPrice } from "../hooks/useMarketData";

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
 * LiveQuote — the current-price ticker, auto-refetching every 30s
 * (matching the backend's quote cache TTL, src/infrastructure/
 * market_data/cache.py) via useCurrentPrice's refetchInterval.
 */
export function LiveQuote({ symbol }: LiveQuoteProps) {
  const { data, isLoading, isError, error } = useCurrentPrice(symbol);

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

  return (
    <Card className="flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-text-secondary">{data.symbol}</p>
        <p className={`text-2xl font-semibold ${gainColorClass(data.price, data.previous_close)}`}>
          {formatMoney(data.price)}
        </p>
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
