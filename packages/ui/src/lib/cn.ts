import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Standard shadcn/ui utility — merges Tailwind classes, resolving conflicts
 * (e.g. two different `p-*` values) in favor of the later one. Using the
 * library combo directly rather than reinventing class merging, per the
 * "prefer a mature library" directive.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
