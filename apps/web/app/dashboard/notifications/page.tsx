"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { NotificationsDashboard } from "../../../features/notifications/components/NotificationsDashboard";
import { useAuthStore } from "../../../store/auth-store";

/**
 * Notifications dashboard — Phase 6 target. Client-side auth guard
 * matching app/dashboard/alerts/page.tsx's exact pattern.
 */
export default function NotificationsPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/login?redirectTo=%2Fdashboard%2Fnotifications");
    }
  }, [isAuthenticated, router]);

  if (!isAuthenticated) {
    return null;
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto max-w-5xl">
        <NotificationsDashboard />
      </div>
    </main>
  );
}
