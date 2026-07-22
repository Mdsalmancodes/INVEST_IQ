// Shared Tailwind preset — design tokens per Document 2 §6.3/§6.3a (post-review
// revision: semantic CSS-variable tokens with light/dark pairs, not flat
// hardcoded hex values). Consumed by apps/web's tailwind.config.ts via `presets`.

/** @type {import('tailwindcss').Config} */
const preset = {
  darkMode: "class", // next-themes' class strategy, per Document 2 §6.3a
  theme: {
    // Mobile-first breakpoint scale — Tailwind defaults, adopted deliberately
    // per Document 2 §6.1a rather than inventing custom values.
    screens: {
      sm: "640px",
      md: "768px",
      lg: "1024px",
      xl: "1280px",
      "2xl": "1536px",
    },
    extend: {
      colors: {
        // Semantic tokens reference CSS variables (defined in globals.css),
        // which swap per light/dark theme — components never reference raw
        // brand hex values directly (Document 2 §6.3a).
        background: "var(--color-background)",
        surface: "var(--color-surface)",
        "text-primary": "var(--color-text-primary)",
        "text-secondary": "var(--color-text-secondary)",
        success: "var(--color-success)",
        primary: {
          DEFAULT: "var(--color-primary)",
          50: "#F5F1FF",
          100: "#EBE3FF",
          500: "#6C3BFF",
          600: "#5B2FE0",
          700: "#4A23B8",
        },
        accent: {
          emerald: "#10B981",
        },
        // Raw brand palette value (Document 1 §palette: "Dark #111827") —
        // intentionally theme-INDEPENDENT (unlike background/surface/
        // text-primary above), for elements that should always render
        // dark regardless of light/dark mode (e.g. SessionExpiredBanner).
        dark: "#111827",
        danger: "#EF4444",
        warning: "#F59E0B",
      },
    },
  },
};

export default preset;
