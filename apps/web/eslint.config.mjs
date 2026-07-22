import { baseConfig } from "@investiq/config/eslint-base.js";
import nextPlugin from "@next/eslint-plugin-next";

/** @type {import('eslint').Linter.Config[]} */
export default [
  ...baseConfig,
  {
    plugins: { "@next/next": nextPlugin },
    rules: {
      ...nextPlugin.configs.recommended.rules,
    },
  },
];
