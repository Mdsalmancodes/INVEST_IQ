"use client";

import { Button, Card } from "@investiq/ui";
import { useEffect } from "react";

/**
 * Dashboard-scoped error boundary — catches render errors anywhere under
 * /dashboard without tearing down the marketing/landing pages' own error
 * boundary scope (app/error.tsx). Offers a "Retry" action plus a link
 * back to the dashboard root, since "go to dashboard" from the global
 * boundary would be circular here.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center p-4">
      <Card className="glass max-w-md text-center">
        <h1 className="text-xl font-semibold text-text-primary">This page hit a snag</h1>
        <p className="mt-2 text-sm text-text-secondary">
          Something went wrong loading this part of the dashboard.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Button variant="secondary" onClick={() => reset()}>
            Try again
          </Button>
          <Button asChild>
            <a href="/dashboard">Back to overview</a>
          </Button>
        </div>
      </Card>
    </div>
  );
}
