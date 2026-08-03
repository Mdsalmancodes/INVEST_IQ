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
  purpleLight: "#8B5FFF",
  purpleDeep: "#4A23B8",
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
    // Glassmorphism tokens (white+purple theme) — translucent surfaces over
    // a soft purple-tinted background wash, per the "premium glassmorphism"
    // design direction. Kept as their own variables (rather than repurposing
    // --color-surface) so existing opaque-surface usage is unaffected;
    // components opt in via the .glass/.glass-strong utility classes below.
    "--glass-bg": "rgba(255, 255, 255, 0.6)",
    "--glass-bg-strong": "rgba(255, 255, 255, 0.75)",
    "--glass-border": "rgba(108, 59, 255, 0.14)",
    "--glass-shadow": "0 8px 32px rgba(108, 59, 255, 0.12)",
    "--gradient-wash":
      "radial-gradient(circle at 15% 0%, rgba(108, 59, 255, 0.10), transparent 45%), " +
      "radial-gradient(circle at 85% 20%, rgba(139, 95, 255, 0.08), transparent 40%)",
  },
  dark: {
    "--color-background": brandPalette.slate900,
    "--color-surface": "#1A2233",
    "--color-text-primary": brandPalette.white,
    "--color-text-secondary": brandPalette.slate400,
    "--color-primary": "#8B5FFF",
    "--color-success": brandPalette.emeraldDark,
    "--glass-bg": "rgba(26, 34, 51, 0.6)",
    "--glass-bg-strong": "rgba(26, 34, 51, 0.78)",
    "--glass-border": "rgba(139, 95, 255, 0.18)",
    "--glass-shadow": "0 8px 32px rgba(0, 0, 0, 0.35)",
    "--gradient-wash":
      "radial-gradient(circle at 15% 0%, rgba(139, 95, 255, 0.16), transparent 45%), " +
      "radial-gradient(circle at 85% 20%, rgba(108, 59, 255, 0.12), transparent 40%)",
  },
} as const;

export type ThemeMode = keyof typeof semanticTokens;
