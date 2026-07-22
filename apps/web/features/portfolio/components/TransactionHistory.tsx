"use client";

import { Card } from "@investiq/ui";
import { useState } from "react";

import { useTransactions } from "../hooks/useTransactions";

export interface TransactionHistoryProps {
  portfolioId: string;
}

const PAGE_SIZE = 20;

const TYPE_LABELS: Record<string, string> = {
  buy: "Buy",
  sell: "Sell",
  dividend: "Dividend",
  split: "Split",
  transfer_in: "Transfer In",
  transfer_out: "Transfer Out",
  deposit: "Deposit",
  withdrawal: "Withdrawal",
};

function formatMoney(value: string | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    Number.parseFloat(value)
  );
}

/**
 * TransactionHistory — paginated list of every transaction recorded
 * against the portfolio (Document 3 §3.4's append-only transaction log).
 * Explicit loading/error/empty states.
 */
export function TransactionHistory({ portfolioId }: TransactionHistoryProps) {
  const [page, setPage] = useState(1);
  const {
    data: result,
    isLoading,
    isError,
    error,
  } = useTransactions(portfolioId, { page, pageSize: PAGE_SIZE });

  if (isLoading) {
    return (
      <Card role="status" aria-live="polite" className="h-64 animate-pulse bg-primary-50">
        <span className="sr-only">Loading transaction history…</span>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
        Failed to load transaction history{error instanceof Error ? `: ${error.message}` : "."}
      </Card>
    );
  }

  if (!result || result.items.length === 0) {
    return (
      <Card className="flex flex-col items-center gap-2 py-12 text-center">
        <p className="text-lg font-medium text-text-primary">No transactions yet</p>
        <p className="text-sm text-text-secondary">
          Transactions you record will appear here in chronological order.
        </p>
      </Card>
    );
  }

  const totalPages = Math.max(1, Math.ceil(result.total_count / result.page_size));

  return (
    <Card className="overflow-x-auto p-0">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-primary-100 text-left text-text-secondary">
            <th className="px-4 py-3 font-medium">Date</th>
            <th className="px-4 py-3 font-medium">Type</th>
            <th className="px-4 py-3 font-medium">Quantity</th>
            <th className="px-4 py-3 font-medium">Price</th>
            <th className="px-4 py-3 font-medium">Fees</th>
            <th className="px-4 py-3 font-medium">Cash Amount</th>
            <th className="px-4 py-3 font-medium">Realized Gain</th>
          </tr>
        </thead>
        <tbody>
          {result.items.map((tx) => (
            <tr key={tx.id} className="border-b border-primary-50 last:border-0">
              <td className="px-4 py-3 text-text-secondary">
                {new Date(tx.executed_at).toLocaleDateString()}
              </td>
              <td className="px-4 py-3">{TYPE_LABELS[tx.type] ?? tx.type}</td>
              <td className="px-4 py-3">{tx.quantity ?? "—"}</td>
              <td className="px-4 py-3">{formatMoney(tx.price)}</td>
              <td className="px-4 py-3">{formatMoney(tx.fees)}</td>
              <td className="px-4 py-3">{formatMoney(tx.cash_amount)}</td>
              <td className="px-4 py-3">{formatMoney(tx.realized_gain ?? null)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {totalPages > 1 && (
        <nav
          aria-label="Transaction history pagination"
          className="flex items-center justify-between border-t border-primary-100 px-4 py-3"
        >
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="text-sm text-primary disabled:cursor-not-allowed disabled:text-text-secondary disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-sm text-text-secondary">
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="text-sm text-primary disabled:cursor-not-allowed disabled:text-text-secondary disabled:opacity-50"
          >
            Next
          </button>
        </nav>
      )}
    </Card>
  );
}
