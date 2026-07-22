"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ApiError, authApi } from "../../../lib/auth-api";

type VerificationStatus = "verifying" | "success" | "error";

function VerifyEmailPageContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<VerificationStatus>("verifying");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setErrorMessage("This verification link is missing or invalid.");
      return;
    }

    let isMounted = true;
    authApi
      .verifyEmail(token)
      .then(() => {
        if (isMounted) setStatus("success");
      })
      .catch((error: unknown) => {
        if (!isMounted) return;
        setStatus("error");
        setErrorMessage(
          error instanceof ApiError
            ? error.message
            : "Something went wrong while verifying your email."
        );
      });

    return () => {
      isMounted = false;
    };
  }, [token]);

  if (status === "verifying") {
    return (
      <p role="status" className="text-center text-sm text-text-primary/70">
        Verifying your email…
      </p>
    );
  }

  if (status === "success") {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <p role="status" className="text-sm text-accent-emerald">
          Your email has been verified successfully.
        </p>
        <Link href="/login" className="text-sm text-primary hover:underline">
          Go to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4 text-center">
      <p role="alert" className="text-sm text-danger">
        {errorMessage}
      </p>
      <Link href="/login" className="text-sm text-primary hover:underline">
        Back to sign in
      </Link>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmailPageContent />
    </Suspense>
  );
}
