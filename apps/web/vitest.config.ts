import { defineConfig } from "vitest/config";

export default defineConfig({
  // Next.js's tsconfig.json intentionally sets jsx: "preserve" (required for
  // Next's own compiler) — Vitest doesn't go through that compiler, so it
  // needs its own esbuild JSX setting here rather than inheriting tsconfig's.
  esbuild: {
    jsx: "automatic",
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["../../packages/ui/src/test-setup.ts"],
    exclude: ["**/node_modules/**", "**/e2e/**"],
  },
});
