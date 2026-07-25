"use client";

import { animate } from "motion/react";
import { useEffect, useRef, useState } from "react";

/**
 * AnimatedNumber — Phase 9 (Real-Time Market Intelligence). Smoothly
 * transitions a displayed numeric value from its previous value to a new
 * one whenever `value` changes, rather than snapping instantly — the
 * "animated number transitions" requirement for live price/portfolio-
 * value/P&L widgets that update over WebSocket. Uses `motion`'s already-
 * installed `animate()` function directly (no new dependency — `motion`
 * is already a dependency of apps/web per package.json, the same one
 * PortfolioSummaryCards.tsx already uses for its card fade-in).
 *
 * Placed under features/realtime/ (not packages/ui) because packages/ui
 * does NOT have `motion` as a dependency (confirmed by reading its
 * package.json before writing this) — adding it there for one primitive
 * would be a heavier change than this component warrants, whereas
 * apps/web already has it. If a future phase needs this primitive
 * shared with another app, promoting it to packages/ui (and adding
 * `motion` there) is the natural next step, not done here since only
 * apps/web needs it today.
 *
 * Renders the animated numeric value through `format` (e.g. currency/
 * percent formatting) so callers keep full control of display formatting
 * — this component only owns the *transition*, not the formatting.
 *
 * A value's very first render does NOT animate from 0 — it snaps
 * directly to the initial value, since animating "from nothing" would
 * misleadingly suggest the value grew from zero.
 */
export interface AnimatedNumberProps {
  value: number;
  format?: (value: number) => string;
  durationSeconds?: number;
  className?: string;
}

export function AnimatedNumber({
  value,
  format = (n) => n.toString(),
  durationSeconds = 0.6,
  className,
}: AnimatedNumberProps) {
  const [displayValue, setDisplayValue] = useState(value);
  const previousValueRef = useRef(value);
  const hasMountedRef = useRef(false);

  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      previousValueRef.current = value;
      setDisplayValue(value);
      return;
    }

    const from = previousValueRef.current;
    if (from === value) return;

    const controls = animate(from, value, {
      duration: durationSeconds,
      ease: "easeOut",
      onUpdate: (latest) => setDisplayValue(latest),
    });

    previousValueRef.current = value;
    return () => controls.stop();
  }, [value, durationSeconds]);

  return <span className={className}>{format(displayValue)}</span>;
}
