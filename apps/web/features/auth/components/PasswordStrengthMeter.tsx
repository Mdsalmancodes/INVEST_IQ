"use client";

import { motion } from "motion/react";
import { useMemo } from "react";

export interface PasswordStrengthMeterProps {
  password: string;
}

type StrengthLevel = "empty" | "weak" | "fair" | "good" | "strong";

/**
 * Client-side password strength ESTIMATE only — a heuristic UX aid, never
 * the actual security boundary (Document 6 §15.2: length-focused policy,
 * common-password blocklist enforced server-side). This component
 * deliberately does NOT duplicate the server's common-password wordlist
 * into the client bundle (Document 6 §15.3's "client validation is UX
 * only" principle) — it estimates strength from length + character-class
 * diversity, which is a reasonable proxy without shipping a security
 * artifact to the browser.
 */
function estimateStrength(password: string): { level: StrengthLevel; score: number } {
  if (password.length === 0) return { level: "empty", score: 0 };

  let score = 0;
  if (password.length >= 10) score += 1;
  if (password.length >= 16) score += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[^a-zA-Z0-9]/.test(password)) score += 1;

  if (score <= 1) return { level: "weak", score };
  if (score === 2) return { level: "fair", score };
  if (score <= 4) return { level: "good", score };
  return { level: "strong", score };
}

const LEVEL_CONFIG: Record<StrengthLevel, { label: string; color: string; widthPct: number }> = {
  empty: { label: "", color: "transparent", widthPct: 0 },
  weak: { label: "Weak", color: "#EF4444", widthPct: 25 },
  fair: { label: "Fair", color: "#F59E0B", widthPct: 50 },
  good: { label: "Good", color: "#6C3BFF", widthPct: 75 },
  strong: { label: "Strong", color: "#10B981", widthPct: 100 },
};

export function PasswordStrengthMeter({ password }: PasswordStrengthMeterProps) {
  const { level } = useMemo(() => estimateStrength(password), [password]);
  const config = LEVEL_CONFIG[level];

  if (level === "empty") return null;

  return (
    <div className="flex flex-col gap-1" aria-live="polite">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-primary-100">
        <motion.div
          className="h-full rounded-full"
          style={{ backgroundColor: config.color }}
          initial={{ width: 0 }}
          animate={{ width: `${config.widthPct}%` }}
          transition={{ duration: 0.25, ease: "easeOut" }}
        />
      </div>
      <span className="text-xs" style={{ color: config.color }}>
        Password strength: {config.label}
      </span>
    </div>
  );
}
