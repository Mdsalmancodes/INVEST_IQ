// Public exports — Document 2 §6.3. Consumers (apps/web) import from
// "@investiq/ui", never from deep paths, so internal reorganization never
// breaks consumers.

export { Button, type ButtonProps } from "./primitives/Button";
export { Card } from "./composite/Card";
export { brandPalette, semanticTokens, type ThemeMode } from "./tokens/colors";
export { cn } from "./lib/cn";
