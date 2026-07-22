"use client";

import Link from "next/link";
import { useState } from "react";

import { RegisterForm } from "../../../features/auth/components/RegisterForm";
import { VerifyEmailNotice } from "../../../features/auth/components/VerifyEmailNotice";

export default function RegisterPage() {
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);

  if (registeredEmail) {
    return <VerifyEmailNotice email={registeredEmail} />;
  }

  return (
    <div className="flex flex-col items-center gap-6">
      <h1 className="text-xl font-semibold text-text-primary">Create your account</h1>
      <RegisterForm onSuccess={setRegisteredEmail} />
      <p className="text-sm text-text-primary/70">
        Already have an account?{" "}
        <Link href="/login" className="text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
