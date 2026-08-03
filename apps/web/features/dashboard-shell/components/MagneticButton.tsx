"use client";

import { Button, type ButtonProps } from "@investiq/ui";
import { motion, useMotionValue, useSpring } from "motion/react";
import { forwardRef, type MouseEvent } from "react";

/**
 * MagneticButton — wraps @investiq/ui's Button with a subtle "magnetic"
 * cursor-attraction effect on hover (the button visually leans toward
 * the pointer within a small radius), one of the "smooth micro-
 * interactions" / "magnetic buttons" premium polish requirements.
 *
 * Uses `motion`'s useMotionValue/useSpring directly (already a
 * dependency, same pattern as AnimatedNumber.tsx) rather than a new
 * dependency. Falls back to the plain Button's behavior for keyboard
 * interaction — the magnetic effect is a pointermove enhancement only,
 * never required to activate the button, so it doesn't affect
 * accessibility or the underlying <button> semantics/props at all.
 */
export interface MagneticButtonProps extends ButtonProps {
  /** How strongly the button follows the pointer, in pixels at max offset. Default 12. */
  strength?: number;
}

export const MagneticButton = forwardRef<HTMLButtonElement, MagneticButtonProps>(
  ({ strength = 12, onMouseMove, onMouseLeave, style, ...props }, ref) => {
    const x = useMotionValue(0);
    const y = useMotionValue(0);
    const springX = useSpring(x, { stiffness: 200, damping: 15, mass: 0.2 });
    const springY = useSpring(y, { stiffness: 200, damping: 15, mass: 0.2 });

    const handleMouseMove = (event: MouseEvent<HTMLButtonElement>) => {
      const rect = event.currentTarget.getBoundingClientRect();
      const offsetX = event.clientX - (rect.left + rect.width / 2);
      const offsetY = event.clientY - (rect.top + rect.height / 2);
      x.set((offsetX / (rect.width / 2)) * strength);
      y.set((offsetY / (rect.height / 2)) * strength);
      onMouseMove?.(event);
    };

    const handleMouseLeave = (event: MouseEvent<HTMLButtonElement>) => {
      x.set(0);
      y.set(0);
      onMouseLeave?.(event);
    };

    return (
      <motion.div style={{ x: springX, y: springY, display: "inline-block" }}>
        <Button
          ref={ref}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          style={style}
          {...props}
        />
      </motion.div>
    );
  }
);
MagneticButton.displayName = "MagneticButton";
