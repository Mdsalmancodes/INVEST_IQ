"use client";

import { Card } from "@investiq/ui";
import { motion } from "motion/react";

import { usePortfolioSummary } from "../hooks/useTransactions";

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
 */
export function PortfolioSummaryCards({ portfolioId }: PortfolioSummaryCardsProps) {
  const { data: summary, isLoading, isError, error } = usePortfolioSummary(portfolioId);

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
    { label: "Total Investment", value: formatMoney(summary.total_investment) },
    { label: "Current Value", value: formatMoney(summary.current_value) },
    {
      label: "Profit / Loss",
      value: formatMoney(summary.profit_loss),
      sub: formatPercent(summary.profit_loss_pct),
      colorClass: gainColorClass(summary.profit_loss),
    },
    {
      label: "Realized Gain",
      value: formatMoney(summary.realized_gain),
      colorClass: gainColorClass(summary.realized_gain),
    },
    {
      label: "Unrealized Gain",
      value: formatMoney(summary.unrealized_gain),
      colorClass: gainColorClass(summary.unrealized_gain),
    },
    { label: "Dividend Income", value: formatMoney(summary.dividend_income) },
    {
      label: "Daily Gain/Loss",
      value: formatMoney(summary.daily_gain),
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
            <p className={`mt-1 text-2xl font-semibold ${card.colorClass ?? "text-text-primary"}`}>
              {card.value}
            </p>
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
    </div>
  );
}
