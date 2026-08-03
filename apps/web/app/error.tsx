"use client";

import { Button, Card } from "@investiq/ui";
import { useEffect } from "react";

/**
 * Root error boundary — Next.js renders this in place of the page tree
 * whenever a render/data-fetching error is thrown beneath it and not
 * already caught by a more specific error.tsx. Previously absent
 * entirely (audit finding), meaning any unhandled render exception fell
 * through to Next's default, unstyled error screen instead of this
 * app's own glassmorphism theme. Must be a client component ("use
 * client") — Next.js error boundaries only work as client components,
 * per the framework's own error.tsx contract.
 */
export default function GlobalError({
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
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="glass max-w-md text-center">
        <h1 className="text-xl font-semibold text-text-primary">Something went wrong</h1>
        <p className="mt-2 text-sm text-text-secondary">
          An unexpected error occurred. You can try again, or head back to the dashboard.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Button variant="secondary" onClick={() => reset()}>
            Try again
          </Button>
          <Button asChild>
            <a href="/dashboard">Go to dashboard</a>
          </Button>
        </div>
      </Card>
    </div>
  );
}
