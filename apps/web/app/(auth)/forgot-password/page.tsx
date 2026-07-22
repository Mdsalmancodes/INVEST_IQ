"use client";

import Link from "next/link";

import { ForgotPasswordForm } from "../../../features/auth/components/ForgotPasswordForm";

export default function ForgotPasswordPage() {
  return (
    <div className="flex flex-col items-center gap-6">
      <h1 className="text-xl font-semibold text-text-primary">Reset your password</h1>
      <p className="text-center text-sm text-text-primary/70">
        Enter the email associated with your account and we&apos;ll send you a link to reset
        your password.
      </p>
      <ForgotPasswordForm />
      <Link href="/login" className="text-sm text-primary hover:underline">
        Back to sign in
      </Link>
    </div>
  );
}
