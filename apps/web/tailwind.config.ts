import type { Config } from "tailwindcss";

// @investiq/config only ships a CommonJS preset (tailwind.config.js
// convention); importing it via a default-interop import keeps this file
// as a proper ES module rather than mixing in a require() call.
import preset from "@investiq/config/tailwind.preset.js";

const config: Config = {
  presets: [preset],
  content: [
    "./app/**/*.{ts,tsx}",
    "./features/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
};

export default config;
