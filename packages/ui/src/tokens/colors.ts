/**
 * Design tokens — Document 2 §6.3/§6.3a (post-review revision).
 *
 * `brandPalette` holds raw hex values (source of truth for the brand).
 * `semanticTokens` maps palette values to light/dark CSS variable pairs —
 * components reference `--color-*` variables (via Tailwind's `bg-background`,
 * `text-text-primary`, etc. per tailwind.preset.js), never raw hex, so theme
 * switching is a CSS-variable swap, not a component rewrite.
 */

export const brandPalette = {
  purple: "#6C3BFF",
  white: "#FFFFFF",
  slate50: "#F8FAFC",
  slate500: "#64748B",
  slate400: "#94A3B8",
  slate900: "#111827",
  emerald: "#10B981",
  emeraldDark: "#34D399",
  red: "#EF4444",
  amber: "#F59E0B",
} as const;

export const semanticTokens = {
  light: {
    "--color-background": brandPalette.slate50,
    "--color-surface": brandPalette.white,
    "--color-text-primary": brandPalette.slate900,
    "--color-text-secondary": brandPalette.slate500,
    "--color-primary": brandPalette.purple,
    "--color-success": brandPalette.emerald,
  },
  dark: {
    "--color-background": brandPalette.slate900,
    "--color-surface": "#1A2233",
    "--color-text-primary": brandPalette.white,
    "--color-text-secondary": brandPalette.slate400,
    "--color-primary": "#8B5FFF",
    "--color-success": brandPalette.emeraldDark,
  },
} as const;

export type ThemeMode = keyof typeof semanticTokens;
