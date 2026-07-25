"use client";

import { Card } from "@investiq/ui";
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useEffect } from "react";

import type { PortfolioSummaryResponse } from "../../../lib/portfolio-api";
import { AnimatedNumber } from "../../realtime/components/AnimatedNumber";
import { useRealtimeConnection } from "../../realtime/hooks/useRealtimeConnection";
import { summaryKeys, usePortfolioSummary } from "../hooks/useTransactions";

export interface PortfolioSummaryCardsProps {
  portfolioId: string;
}

function formatMoney(value: string, currency = "USD"): string {
  const amount = Number.parseFloat(value);
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
}

function formatPercent(value: string): string {
  const pct = Number.parseFloat(value);
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function gainColorClass(value: string): string {
  const num = Number.parseFloat(value);
  if (num > 0) return "text-success";
  if (num < 0) return "text-danger";
  return "text-text-secondary";
}

/**
 * PortfolioSummaryCards — the dashboard's headline numbers: Total
 * Investment, Current Value, Profit/Loss (with %), Realized Gain,
 * Unrealized Gain, Dividend Income, Daily Gain/Loss. Explicit
 * loading/error/empty states per the founder's Phase 3 requirement.
 * Initial load + fallback polling via usePortfolioSummary (Phase 3,
 * UNMODIFIED — this component works identically with the WebSocket
 * entirely offline).
 *
 * Phase 9 ADDITIVE ENHANCEMENT: subscribes to `portfolio:{portfolioId}`
 * over the shared WebSocket connection and patches the SAME TanStack
 * Query cache entry usePortfolioSummary reads from whenever a fresh
 * tick arrives (PortfolioStreamingService's own _summary_to_payload
 * shape is a compatible subset of PortfolioSummaryResponse's top-level
 * fields, plus a NEW `sector_allocation` array satisfying the "Sector
 * Allocation"/"Investment Distribution" requirement — holdings/
 * holdings_missing_price are preserved from the previous cache value
 * since the WS tick doesn't recompute the full per-holding breakdown).
 * Each headline number renders through AnimatedNumber so a live update
 * transitions smoothly instead of snapping.
 */
export function PortfolioSummaryCards({ portfolioId }: PortfolioSummaryCardsProps) {
  const { data: summary, isLoading, isError, error } = usePortfolioSummary(portfolioId);
  const queryClient = useQueryClient();
  const { subscribe } = useRealtimeConnection();

  useEffect(() => {
    return subscribe(`portfolio:${portfolioId}`, (envelope) => {
      const tick = envelope.data as
        | (Omit<PortfolioSummaryResponse, "holdings" | "holdings_missing_price" | "sector_allocation"> & {
            sector_allocation: Array<{
              sector: string;
              market_value: string;
              allocation_pct: string;
            }>;
          })
        | undefined;
      if (!tick || tick.portfolio_id !== portfolioId) return;

      queryClient.setQueryData<PortfolioSummaryResponse>(
        summaryKeys.detail(portfolioId),
        (previous) => ({
          ...tick,
          holdings: previous?.holdings ?? [],
          holdings_missing_price: previous?.holdings_missing_price ?? [],
        })
      );
    });
  }, [portfolioId, subscribe, queryClient]);

  if (isLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="h-24 animate-pulse bg-primary-50" aria-hidden="true" />
        ))}
        <span className="sr-only">Loading portfolio summary…</span>
      </div>
    );
  }

  if (isError) {
    return (
      <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
        Failed to load portfolio summary
        {error instanceof Error ? `: ${error.message}` : "."}
      </Card>
    );
  }

  if (!summary) {
    return null;
  }

  const cards = [
    { label: "Total Investment", value: Number.parseFloat(summary.total_investment) },
    { label: "Current Value", value: Number.parseFloat(summary.current_value) },
    {
      label: "Profit / Loss",
      value: Number.parseFloat(summary.profit_loss),
      sub: formatPercent(summary.profit_loss_pct),
      colorClass: gainColorClass(summary.profit_loss),
    },
    {
      label: "Realized Gain",
      value: Number.parseFloat(summary.realized_gain),
      colorClass: gainColorClass(summary.realized_gain),
    },
    {
      label: "Unrealized Gain",
      value: Number.parseFloat(summary.unrealized_gain),
      colorClass: gainColorClass(summary.unrealized_gain),
    },
    { label: "Dividend Income", value: Number.parseFloat(summary.dividend_income) },
    {
      label: "Daily Gain/Loss",
      value: Number.parseFloat(summary.daily_gain),
      colorClass: gainColorClass(summary.daily_gain),
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card, index) => (
        <motion.div
          key={card.label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: index * 0.03 }}
        >
          <Card>
            <p className="text-sm font-medium text-text-secondary">{card.label}</p>
            <AnimatedNumber
              value={card.value}
              format={(n) => formatMoney(n.toString())}
              className={`mt-1 block text-2xl font-semibold ${card.colorClass ?? "text-text-primary"}`}
            />
            {card.sub && <p className={`text-sm ${card.colorClass ?? ""}`}>{card.sub}</p>}
          </Card>
        </motion.div>
      ))}
      {summary.holdings_missing_price.length > 0 && (
        <Card
          role="status"
          className="col-span-full border-warning/40 bg-warning/5 text-sm text-text-secondary"
        >
          {summary.holdings_missing_price.length} holding(s) are missing current price data and
          are excluded from Current Value, Unrealized Gain, Allocation %, and Daily Gain/Loss.
        </Card>
      )}
      {summary.sector_allocation && summary.sector_allocation.length > 0 && (
        <Card className="col-span-full">
          <p className="text-sm font-medium text-text-secondary">Sector Allocation</p>
          <ul className="mt-2 space-y-1">
            {summary.sector_allocation.map((entry) => (
              <li key={entry.sector} className="flex items-center justify-between text-sm">
                <span className="text-text-primary">{entry.sector}</span>
                <span className="text-text-secondary">
                  {formatMoney(entry.market_value)} ({Number.parseFloat(entry.allocation_pct).toFixed(1)}%)
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
