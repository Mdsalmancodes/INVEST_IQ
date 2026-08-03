"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AlertsDashboard } from "../../../features/alerts/components/AlertsDashboard";
import { useAuthStore } from "../../../store/auth-store";

/**
 * Alerts dashboard — Phase 6 target. Client-side auth guard matching
 * app/dashboard/watchlists/page.tsx's exact pattern (redirects to /login
 * if there's no access token in memory — the same disclosed BFF-cookie
 * limitation carried forward from Phase 2/3/5).
 */
export default function AlertsPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isBootstrapping = useAuthStore((state) => state.isBootstrapping);

  useEffect(() => {
    if (!isBootstrapping && !isAuthenticated) {
      router.replace("/login?redirectTo=%2Fdashboard%2Falerts");
    }
  }, [isAuthenticated, isBootstrapping, router]);

  if (isBootstrapping || !isAuthenticated) {
    return null;
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto max-w-5xl">
        <AlertsDashboard />
      </div>
    </main>
  );
}
