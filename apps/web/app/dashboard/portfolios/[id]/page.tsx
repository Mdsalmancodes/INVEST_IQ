"use client";

import { Button } from "@investiq/ui";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AddTransactionDialog } from "../../../../features/portfolio/components/AddTransactionDialog";
import { HoldingsTable } from "../../../../features/portfolio/components/HoldingsTable";
import { PortfolioSummaryCards } from "../../../../features/portfolio/components/PortfolioSummaryCards";
import { TransactionHistory } from "../../../../features/portfolio/components/TransactionHistory";
import { usePortfolio } from "../../../../features/portfolio/hooks/usePortfolios";
import { useAuthStore } from "../../../../store/auth-store";

/**
 * Portfolio detail dashboard — wires together PortfolioSummaryCards,
 * HoldingsTable, TransactionHistory, and AddTransactionDialog for a
 * single portfolio (Document 8 §24 roadmap target for Phase 3).
 */
export default function PortfolioDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const portfolioId = params.id;
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const { data: portfolio, isLoading, isError, error } = usePortfolio(portfolioId);
  const [isAddTransactionOpen, setIsAddTransactionOpen] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace(`/login?redirectTo=%2Fdashboard%2Fportfolios%2F${portfolioId}`);
    }
  }, [isAuthenticated, router, portfolioId]);

  if (!isAuthenticated) {
    return null;
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto max-w-5xl">
        <div className="flex items-center justify-between">
          <div>
            <Link href="/dashboard/portfolios" className="text-sm text-primary">
              ← Back to portfolios
            </Link>
            {isLoading && <p className="mt-1 text-2xl font-semibold text-text-primary">Loading…</p>}
            {isError && (
              <p role="alert" className="mt-1 text-danger">
                Failed to load portfolio{error instanceof Error ? `: ${error.message}` : "."}
              </p>
            )}
            {portfolio && (
              <h1 className="mt-1 text-2xl font-semibold text-text-primary">{portfolio.name}</h1>
            )}
          </div>
          <Button onClick={() => setIsAddTransactionOpen(true)}>Add Transaction</Button>
        </div>

        <div className="mt-6 flex flex-col gap-6">
          <PortfolioSummaryCards portfolioId={portfolioId} />
          <HoldingsTable portfolioId={portfolioId} />
          <TransactionHistory portfolioId={portfolioId} />
        </div>
      </div>

      <AddTransactionDialog
        portfolioId={portfolioId}
        isOpen={isAddTransactionOpen}
        onClose={() => setIsAddTransactionOpen(false)}
      />
    </main>
  );
}
