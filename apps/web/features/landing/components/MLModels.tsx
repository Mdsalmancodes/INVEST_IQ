"use client";

import { Card } from "@investiq/ui";
import { motion } from "motion/react";

/**
 * MLModels — showcases the 6 real model families the AI service actually
 * runs (apps/ai-service/src/domain/ml/value_objects.py's ModelFamily
 * Literal type is the source of truth for this list), each with its real
 * weight in the Decision Engine's ensemble
 * (apps/ai-service/src/application/ml/decision_engine.py's _BASE_WEIGHTS).
 */
const MODELS = [
  { name: "LSTM", type: "Deep Learning", weight: 0.25, description: "Sequential price pattern learning" },
  { name: "ARIMA", type: "Statistical", weight: 0.15, description: "Classical time-series forecasting" },
  { name: "Prophet", type: "Statistical", weight: 0.15, description: "Trend + seasonality decomposition" },
  { name: "Random Forest", type: "Ensemble", weight: 0.15, description: "Non-linear feature-based prediction" },
  { name: "XGBoost", type: "Ensemble", weight: 0.2, description: "Gradient-boosted decision trees" },
  { name: "FinBERT", type: "NLP", weight: 0.1, description: "Financial text sentiment scoring" },
] as const;

export function MLModels() {
  return (
    <section id="ml-models" className="px-4 py-20">
      <div className="mx-auto max-w-6xl">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold text-text-primary sm:text-4xl">
            Six models. One decision.
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-text-secondary">
            The Hybrid Decision Engine weighs every model's signal by confidence and
            historical accuracy — no single model ever makes the call alone.
          </p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {MODELS.map((model, i) => (
            <motion.div
              key={model.name}
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.4, delay: i * 0.06 }}
            >
              <Card className="h-full">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-text-primary">{model.name}</h3>
                    <span className="text-xs text-text-secondary">{model.type}</span>
                  </div>
                  <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                    {Math.round(model.weight * 100)}%
                  </span>
                </div>
                <p className="mt-3 text-sm text-text-secondary">{model.description}</p>
                <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-primary/10">
                  <motion.div
                    className="h-full rounded-full bg-primary"
                    initial={{ width: 0 }}
                    whileInView={{ width: `${model.weight * 100 * 4}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.8, delay: 0.2 + i * 0.06, ease: "easeOut" }}
                  />
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
