"use client";

import { Card } from "@investiq/ui";
import { motion } from "motion/react";

/**
 * SentimentAnalysis — landing showcase for the FinBERT-powered sentiment
 * feature (features/ai/components/SentimentDashboard.tsx is the real,
 * authenticated version of this inside the dashboard). This section uses
 * static illustrative examples, not a live API call — the landing page
 * is intentionally unauthenticated/public, matching every other section
 * here, and the real feature is one click away after signing in.
 */
const EXAMPLES = [
  {
    label: "positive" as const,
    confidence: 0.955,
    text: "Apple reported strong quarterly earnings beating analyst expectations.",
  },
  {
    label: "neutral" as const,
    confidence: 0.71,
    text: "The Federal Reserve held interest rates steady in its latest meeting.",
  },
  {
    label: "negative" as const,
    confidence: 0.88,
    text: "Supply chain disruptions continue to weigh on quarterly production targets.",
  },
] as const;

const LABEL_STYLES = {
  positive: "bg-success/10 text-success",
  neutral: "bg-text-secondary/10 text-text-secondary",
  negative: "bg-danger/10 text-danger",
} as const;

export function SentimentAnalysis() {
  return (
    <section id="sentiment" className="px-4 py-20">
      <div className="mx-auto max-w-6xl">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold text-text-primary sm:text-4xl">
            Know the market&apos;s mood
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-text-secondary">
            FinBERT — a domain-specific model trained on financial text — scores news
            and headlines as positive, neutral, or negative in real time.
          </p>
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {EXAMPLES.map((example, i) => (
            <motion.div
              key={example.text}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
            >
              <Card className="flex h-full flex-col justify-between">
                <p className="text-sm text-text-primary">&ldquo;{example.text}&rdquo;</p>
                <div className="mt-4 flex items-center justify-between">
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold capitalize ${LABEL_STYLES[example.label]}`}
                  >
                    {example.label}
                  </span>
                  <span className="text-xs text-text-secondary">
                    {Math.round(example.confidence * 100)}% confidence
                  </span>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
