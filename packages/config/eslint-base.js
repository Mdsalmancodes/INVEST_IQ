// Shared ESLint flat config base. Per Document 8 §20.1: strict mode, no `any`
// (enforced as an error, not a warning), consistent import ordering.
// Consuming apps extend this and layer framework-specific config on top
// (e.g. apps/web adds eslint-config-next).

import js from "@eslint/js";
import tseslint from "typescript-eslint";
import jsxA11y from "eslint-plugin-jsx-a11y";

/** @type {import('eslint').Linter.Config[]} */
export const baseConfig = [
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    plugins: { "jsx-a11y": jsxA11y },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/consistent-type-imports": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // Accessibility rules enforced at lint time per Document 2 §6.5's
      // component-level accessibility standards (this is the regression
      // guard referenced there, not the sole spec).
      ...jsxA11y.configs.recommended.rules,
    },
  },
  {
    ignores: [
      "**/node_modules/**",
      "**/.next/**",
      "**/dist/**",
      "**/build/**",
      "**/.turbo/**",
      "**/coverage/**",
      "**/storybook-static/**",
    ],
  },
];

export default baseConfig;
