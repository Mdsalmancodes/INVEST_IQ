"use client";

import { Button } from "@investiq/ui";
import { motion } from "motion/react";
import { useState } from "react";

import { authApi } from "../../../lib/auth-api";

export interface VerifyEmailNoticeProps {
  email: string;
}

/**
 * Shown after registration — "please check your email" state, with a
 * resend action. Distinct from the /verify-email PAGE (which handles the
 * token-in-URL flow) — this component is the pre-click waiting state.
 */
export function VerifyEmailNotice({ email }: VerifyEmailNoticeProps) {
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const handleResend = async () => {
    setStatus("sending");
    try {
      await authApi.requestEmailVerification(email);
      setStatus("sent");
    } catch {
      // Enumeration-safe endpoint always returns 200 with a generic message
      // regardless of whether the account exists (Document 6 §15.1) — a
      // caught error here means something else went wrong (network, 5xx),
      // which is still surfaced to the user without leaking account existence.
      setStatus("error");
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex w-full max-w-sm flex-col items-center gap-4 text-center"
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary-50">
        <svg
          aria-hidden="true"
          className="h-8 w-8 text-primary"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
          />
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-text-primary">Check your email</h2>
      <p className="text-sm text-text-primary/70">
        We&apos;ve sent a verification link to <strong>{email}</strong>. Click the link to
        activate your account.
      </p>

      {status === "sent" && (
        <p role="status" className="text-sm text-accent-emerald">
          Verification email sent again.
        </p>
      )}
      {status === "error" && (
        <p role="alert" className="text-sm text-danger">
          Couldn&apos;t resend the email. Please try again.
        </p>
      )}

      <Button
        variant="secondary"
        onClick={handleResend}
        disabled={status === "sending"}
      >
        {status === "sending" ? "Resending…" : "Resend email"}
      </Button>
    </motion.div>
  );
}
