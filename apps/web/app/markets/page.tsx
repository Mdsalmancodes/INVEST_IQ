"use client";

import { useRouter } from "next/navigation";

import { StockSearch } from "../../features/market-data/components/StockSearch";

/**
 * Markets landing page — public stock search, no auth required (per
 * market_data_router.py's disclosed unauthenticated design). Lives
 * OUTSIDE /dashboard deliberately: middleware.ts's matcher only covers
 * /dashboard/:path*, so this page (and /markets/[symbol]) are correctly
 * reachable without a session, matching real trading platforms where
 * looking up a stock quote doesn't require an account.
 */
export default function MarketsPage() {
  const router = useRouter();

  return (
    <main className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto max-w-2xl">
        <h1 className="text-2xl font-semibold text-text-primary">Markets</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Search for a stock to see its price, chart, and corporate actions.
        </p>
        <div className="mt-6">
          <StockSearch onSelect={(symbol) => router.push(`/markets/${symbol}`)} />
        </div>
      </div>
    </main>
  );
}
