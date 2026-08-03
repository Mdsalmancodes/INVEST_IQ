"use client";

import { Card } from "@investiq/ui";
import { motion } from "motion/react";

/**
 * LiveDashboardPreview — a static, illustrative mockup of the real
 * authenticated dashboard (app/dashboard/portfolios/page.tsx +
 * features/portfolio/components/PortfolioSummaryCards.tsx are the real
 * thing). Deliberately NOT wired to any live API: the landing page is
 * public/unauthenticated, and lib/portfolio-api.ts's authorizedRequest
 * would just 401 for a logged-out visitor — showing a realistic static
 * preview here (clearly a marketing mockup, not real user data) is the
 * correct approach, matching how Stripe/Linear/Vercel's own landing
 * pages preview their product with illustrative, not live, data.
 */
const HOLDINGS = [
  { symbol: "AAPL", value: "$12,480.00", change: "+2.4%", positive: true },
  { symbol: "MSFT", value: "$8,120.50", change: "+1.1%", positive: true },
  { symbol: "TSLA", value: "$4,905.20", change: "-0.8%", positive: false },
] as const;

export function LiveDashboardPreview() {
  return (
    <section id="dashboard-preview" className="px-4 py-20">
      <div className="mx-auto max-w-6xl">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold text-text-primary sm:text-4xl">
            Your portfolio, always in view
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-text-secondary">
            Real-time valuation, AI recommendations, and live quotes — all in one
            glassmorphic dashboard.
          </p>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        >
          <Card className="glass-strong mx-auto max-w-4xl p-4 sm:p-6">
            <div className="mb-4 flex items-center justify-between">
              <span className="text-sm font-semibold text-text-secondary">
                Portfolio Overview
              </span>
              <span className="flex items-center gap-1.5 text-xs text-success">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
                Live
              </span>
            </div>

            <div className="mb-6">
              <span className="text-3xl font-bold text-text-primary">$25,505.70</span>
              <span className="ml-2 text-sm font-semibold text-success">+3.2% today</span>
            </div>

            <div className="flex flex-col gap-2">
              {HOLDINGS.map((holding, i) => (
                <motion.div
                  key={holding.symbol}
                  initial={{ opacity: 0, x: -12 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4, delay: 0.2 + i * 0.08 }}
                  className="flex items-center justify-between rounded-lg px-3 py-2.5 hover:bg-primary/5"
                >
                  <span className="font-medium text-text-primary">{holding.symbol}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-text-secondary">{holding.value}</span>
                    <span
                      className={`text-sm font-semibold ${
                        holding.positive ? "text-success" : "text-danger"
                      }`}
                    >
                      {holding.change}
                    </span>
                  </div>
                </motion.div>
              ))}
            </div>
          </Card>
        </motion.div>
      </div>
    </section>
  );
}
