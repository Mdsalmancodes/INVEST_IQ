"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { ResetPasswordForm } from "../../../features/auth/components/ResetPasswordForm";

function ResetPasswordPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [isDone, setIsDone] = useState(false);

  if (!token) {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <p role="alert" className="text-sm text-danger">
          This password reset link is missing or invalid. Please request a new one.
        </p>
        <Link href="/forgot-password" className="text-sm text-primary hover:underline">
          Request a new link
        </Link>
      </div>
    );
  }

  if (isDone) {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <p role="status" className="text-sm text-accent-emerald">
          Your password has been reset. Please sign in with your new password.
        </p>
        <Link href="/login" className="text-sm text-primary hover:underline">
          Go to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-6">
      <h1 className="text-xl font-semibold text-text-primary">Set a new password</h1>
      <ResetPasswordForm
        token={token}
        onSuccess={() => {
          setIsDone(true);
          setTimeout(() => router.push("/login"), 2500);
        }}
      />
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetPasswordPageContent />
    </Suspense>
  );
}
