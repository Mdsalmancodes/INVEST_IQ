"use client";

import { Card } from "@investiq/ui";

import { usePortfolioSummary } from "../hooks/useTransactions";

export interface HoldingsTableProps {
  portfolioId: string;
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
 * HoldingsTable — per-instrument breakdown (quantity, average buy price,
 * current price, market value, unrealized gain, allocation %, daily
 * gain/loss). Uses the summary endpoint (not the plain holdings endpoint)
 * since the table needs the calculated fields, not just quantity/cost.
 */
export function HoldingsTable({ portfolioId }: HoldingsTableProps) {
  const { data: summary, isLoading, isError, error } = usePortfolioSummary(portfolioId);

  if (isLoading) {
    return (
      <Card role="status" aria-live="polite" className="h-64 animate-pulse bg-primary-50">
        <span className="sr-only">Loading holdings…</span>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
        Failed to load holdings{error instanceof Error ? `: ${error.message}` : "."}
      </Card>
    );
  }

  if (!summary || summary.holdings.length === 0) {
    return (
      <Card className="flex flex-col items-center gap-2 py-12 text-center">
        <p className="text-lg font-medium text-text-primary">No holdings yet</p>
        <p className="text-sm text-text-secondary">
          Add a buy transaction to start tracking a position in this portfolio.
        </p>
      </Card>
    );
  }

  return (
    <Card className="overflow-x-auto p-0">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-primary-100 text-left text-text-secondary">
            <th className="px-4 py-3 font-medium">Instrument</th>
            <th className="px-4 py-3 font-medium">Quantity</th>
            <th className="px-4 py-3 font-medium">Avg. Buy Price</th>
            <th className="px-4 py-3 font-medium">Current Price</th>
            <th className="px-4 py-3 font-medium">Market Value</th>
            <th className="px-4 py-3 font-medium">Unrealized Gain</th>
            <th className="px-4 py-3 font-medium">Allocation</th>
            <th className="px-4 py-3 font-medium">Daily Gain/Loss</th>
          </tr>
        </thead>
        <tbody>
          {summary.holdings.map((holding) => (
            <tr key={holding.instrument_id} className="border-b border-primary-50 last:border-0">
              <td className="px-4 py-3 font-mono text-xs text-text-secondary">
                {holding.instrument_id.slice(0, 8)}
              </td>
              <td className="px-4 py-3">{holding.quantity}</td>
              <td className="px-4 py-3">{formatMoney(holding.average_buy_price)}</td>
              <td className="px-4 py-3">{formatMoney(holding.current_price)}</td>
              <td className="px-4 py-3">{formatMoney(holding.market_value)}</td>
              <td className={`px-4 py-3 ${gainColorClass(holding.unrealized_gain)}`}>
                {formatMoney(holding.unrealized_gain)}
              </td>
              <td className="px-4 py-3">{formatPercent(holding.allocation_pct)}</td>
              <td className={`px-4 py-3 ${gainColorClass(holding.daily_gain)}`}>
                {formatMoney(holding.daily_gain)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
