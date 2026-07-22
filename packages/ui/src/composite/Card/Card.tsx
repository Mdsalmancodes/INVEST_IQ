import { forwardRef } from "react";

import { cn } from "../../lib/cn";

/**
 * Card composite — basic surface container. Per Document 2 §6.3, composites
 * build on primitives/design tokens; this one is intentionally minimal in
 * Phase 1 (StatCard, DataTable, etc. are populated as the features that need
 * them are built, per the roadmap).
 */
export const Card = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("rounded-lg border border-primary-100 bg-surface p-6 shadow-sm", className)}
      {...props}
    />
  )
);
Card.displayName = "Card";
