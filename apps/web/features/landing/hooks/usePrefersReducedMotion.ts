"use client";

import { useEffect, useState } from "react";

/**
 * usePrefersReducedMotion — tracks the `(prefers-reduced-motion: reduce)`
 * media query, per the production audit's accessibility finding:
 * AnimatedBackground.tsx's docstring previously claimed "respects
 * prefers-reduced-motion implicitly by being low-amplitude" without any
 * actual media-query check backing that claim. Returns `false` during
 * SSR/initial render (matchMedia isn't available server-side) and updates
 * reactively if the user changes their OS-level setting while the page
 * is open.
 */
export function usePrefersReducedMotion(): boolean {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReducedMotion(mediaQuery.matches);

    const handleChange = (event: MediaQueryListEvent) => {
      setPrefersReducedMotion(event.matches);
    };
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  return prefersReducedMotion;
}
