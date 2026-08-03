"use client";

import { Card } from "@investiq/ui";
import { createPortfolioSchema, type CreatePortfolioFormValues } from "@investiq/validation";
import { zodResolver } from "@hookform/resolvers/zod";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "../../../lib/auth-api";
import { useAuthStore } from "../../../store/auth-store";
import { useCreatePortfolio, usePortfolios } from "../../../features/portfolio/hooks/usePortfolios";
import { MagneticButton } from "../../../features/dashboard-shell/components/MagneticButton";

/**
 * Portfolio list dashboard — Document 8 §24's roadmap target for Phase 3.
 * Client-side auth guard: redirects to /login if there's no access token
 * in memory. This is the same disclosed-limitation view-layer guard
 * pattern used elsewhere (Phase 2 verification report's known-issues
 * section) since the middleware.ts server-side cookie check is not yet
 * functional (BFF cookie route not built) — not a new gap introduced here.
 */
export default function PortfoliosPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isBootstrapping = useAuthStore((state) => state.isBootstrapping);
  const { data, isLoading, isError, error } = usePortfolios();
  const createPortfolio = useCreatePortfolio();
  const [serverError, setServerError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreatePortfolioFormValues>({
    resolver: zodResolver(createPortfolioSchema),
    defaultValues: { baseCurrency: "USD", isPaper: true },
  });

  useEffect(() => {
    // isBootstrapping guards against a flash-redirect on every full-page
    // reload: useSilentSessionBootstrap (app/providers.tsx) needs one
    // async round-trip to /api/bff/refresh to restore isAuthenticated
    // from the httpOnly refresh-token cookie — without this check, this
    // effect would redirect to /login during that brief window even for
    // an already-logged-in user, on every reload.
    if (!isBootstrapping && !isAuthenticated) {
      router.replace("/login?redirectTo=%2Fdashboard%2Fportfolios");
    }
  }, [isAuthenticated, isBootstrapping, router]);

  if (isBootstrapping || !isAuthenticated) {
    return null;
  }

  const onCreate = async (values: CreatePortfolioFormValues) => {
    setServerError(null);
    try {
      await createPortfolio.mutateAsync({
        name: values.name,
        base_currency: values.baseCurrency,
        is_paper: values.isPaper,
      });
      reset();
      setShowCreateForm(false);
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Failed to create portfolio.");
    }
  };

  return (
    <main className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-text-primary">Your Portfolios</h1>
          <MagneticButton onClick={() => setShowCreateForm((v) => !v)}>
            {showCreateForm ? "Cancel" : "New Portfolio"}
          </MagneticButton>
        </div>

        {showCreateForm && (
          <motion.form
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            onSubmit={handleSubmit(onCreate)}
            noValidate
            className="glass mt-4 flex flex-col gap-3 rounded-lg p-4"
          >
            <div className="flex flex-col gap-1">
              <label htmlFor="name" className="text-sm font-medium text-text-primary">
                Portfolio Name
              </label>
              <input
                id="name"
                type="text"
                className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                aria-invalid={errors.name ? "true" : "false"}
                {...register("name")}
              />
              {errors.name && (
                <p role="alert" className="text-sm text-danger">
                  {errors.name.message}
                </p>
              )}
            </div>
            {serverError && (
              <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
                {serverError}
              </p>
            )}
            <MagneticButton type="submit" disabled={isSubmitting} className="self-end">
              {isSubmitting ? "Creating…" : "Create Portfolio"}
            </MagneticButton>
          </motion.form>
        )}

        <div className="mt-6">
          {isLoading && (
            <div role="status" aria-live="polite" className="flex flex-col gap-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Card key={i} className="h-16 animate-pulse bg-primary-50" aria-hidden="true" />
              ))}
              <span className="sr-only">Loading portfolios…</span>
            </div>
          )}

          {isError && (
            <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
              Failed to load portfolios{error instanceof Error ? `: ${error.message}` : "."}
            </Card>
          )}

          {data && data.items.length === 0 && (
            <Card className="flex flex-col items-center gap-2 py-12 text-center">
              <p className="text-lg font-medium text-text-primary">No portfolios yet</p>
              <p className="text-sm text-text-secondary">
                Create your first portfolio to start tracking investments.
              </p>
            </Card>
          )}

          {data && data.items.length > 0 && (
            <div className="flex flex-col gap-3">
              {data.items.map((portfolio, index) => (
                <motion.div
                  key={portfolio.id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: index * 0.05 }}
                >
                  <Link href={`/dashboard/portfolios/${portfolio.id}`}>
                    <Card className="flex items-center justify-between transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg">
                      <div>
                        <p className="font-medium text-text-primary">{portfolio.name}</p>
                        <p className="text-sm text-text-secondary">
                          {portfolio.base_currency} · {portfolio.is_paper ? "Paper" : "Live"}
                        </p>
                      </div>
                    </Card>
                  </Link>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
