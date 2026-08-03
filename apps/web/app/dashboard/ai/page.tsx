"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AIDashboard } from "../../../features/ai/components/AIDashboard";
import { useAuthStore } from "../../../store/auth-store";

/**
 * AI Insights dashboard — Phase 7 target. Client-side auth guard
 * matching app/dashboard/watchlists/page.tsx's exact pattern (redirects
 * to /login if there's no access token in memory) for consistency with
 * the rest of /dashboard/*'s navigation shell, even though the
 * underlying ai-service calls themselves are unauthenticated (disclosed
 * in docs/phase-7/known-issues.md) — this guard protects the page
 * *route* the same way every other dashboard page is protected, it does
 * not and cannot add authorization to ai-service's REST API itself.
 */
export default function AIInsightsPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isBootstrapping = useAuthStore((state) => state.isBootstrapping);

  useEffect(() => {
    if (!isBootstrapping && !isAuthenticated) {
      router.replace("/login?redirectTo=%2Fdashboard%2Fai");
    }
  }, [isAuthenticated, isBootstrapping, router]);

  if (isBootstrapping || !isAuthenticated) {
    return null;
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto max-w-5xl">
        <AIDashboard />
      </div>
    </main>
  );
}
