"use client";

import { Card } from "@investiq/ui";
import { motion } from "motion/react";

/**
 * Features — 6-card grid summarizing the platform's core capabilities.
 * Each card is a real feature of the shipped product (portfolio
 * management, watchlists, AI recommendations, real-time streaming,
 * alerts, explainable AI) — not aspirational copy, per the "don't remove
 * existing functionality" spirit extended to "don't market functionality
 * that doesn't exist."
 */
const FEATURES = [
  {
    title: "Portfolio Intelligence",
    description:
      "Track holdings, transactions, and performance across paper and live portfolios with real-time valuation.",
    icon: "📊",
  },
  {
    title: "6 ML Models",
    description:
      "LSTM, ARIMA, Prophet, Random Forest, XGBoost, and FinBERT combine into a single ensemble recommendation.",
    icon: "🧠",
  },
  {
    title: "Explainable AI",
    description:
      "Every recommendation ships with SHAP-based feature contributions — see exactly why the model decided.",
    icon: "🔍",
  },
  {
    title: "Real-Time Streaming",
    description:
      "Live quotes, watchlists, and AI predictions push instantly over WebSocket — no manual refresh needed.",
    icon: "⚡",
  },
  {
    title: "Smart Alerts",
    description:
      "Price, percentage-change, and RSI-threshold alerts trigger instantly and notify you the moment they fire.",
    icon: "🔔",
  },
  {
    title: "Sentiment Analysis",
    description:
      "FinBERT-powered sentiment scoring on news and text gives you the market's mood, not just its price.",
    icon: "💬",
  },
] as const;

const cardVariants = {
  hidden: { opacity: 0, y: 24 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, delay: i * 0.08, ease: "easeOut" as const },
  }),
};

export function Features() {
  return (
    <section id="features" className="px-4 py-20">
      <div className="mx-auto max-w-6xl">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold text-text-primary sm:text-4xl">
            Everything you need to invest with confidence
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-text-secondary">
            One platform. Six models. Zero guesswork.
          </p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature, i) => (
            <motion.div
              key={feature.title}
              custom={i}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-80px" }}
              variants={cardVariants}
            >
              <Card className="h-full transition-transform duration-300 hover:-translate-y-1">
                <span className="text-3xl">{feature.icon}</span>
                <h3 className="mt-4 text-lg font-semibold text-text-primary">
                  {feature.title}
                </h3>
                <p className="mt-2 text-sm text-text-secondary">{feature.description}</p>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
