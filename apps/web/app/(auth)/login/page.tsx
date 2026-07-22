"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { LoginForm } from "../../../features/auth/components/LoginForm";
import { useAuthStore } from "../../../store/auth-store";

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setAccessToken = useAuthStore((state) => state.setAccessToken);

  const handleSuccess = (accessToken: string) => {
    setAccessToken(accessToken);
    const redirectTo = searchParams.get("redirectTo") ?? "/dashboard";
    router.push(redirectTo);
  };

  return (
    <div className="flex flex-col items-center gap-6">
      <h1 className="text-xl font-semibold text-text-primary">Welcome back</h1>
      <LoginForm onSuccess={handleSuccess} />
      <div className="flex flex-col items-center gap-2 text-sm">
        <Link href="/forgot-password" className="text-primary hover:underline">
          Forgot your password?
        </Link>
        <p className="text-text-primary/70">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-primary hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  // useSearchParams requires a Suspense boundary per Next.js App Router
  // (accessing the redirectTo query param during static generation would
  // otherwise throw — this page is CSR per Document 2 §6.1 anyway, but the
  // boundary is required regardless).
  return (
    <Suspense>
      <LoginPageContent />
    </Suspense>
  );
}
