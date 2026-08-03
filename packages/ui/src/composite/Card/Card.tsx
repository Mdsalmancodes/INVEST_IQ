import { forwardRef } from "react";

import { cn } from "../../lib/cn";

/**
 * Card composite — glassmorphism surface container (translucent
 * background + backdrop blur + soft purple-tinted border/shadow, per the
 * white+purple glassmorphism theme direction). Falls back gracefully to
 * an opaque surface in browsers without backdrop-filter support since
 * --glass-bg is already partially-opaque on its own.
 */
export const Card = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("glass rounded-xl p-6 transition-shadow duration-300", className)}
      {...props}
    />
  )
);
Card.displayName = "Card";
