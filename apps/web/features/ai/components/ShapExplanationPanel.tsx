"use client";

import { Card } from "@investiq/ui";

import type { ExplainabilityResponse } from "../../../lib/ai-api";

export interface ShapExplanationPanelProps {
  explainability: ExplainabilityResponse;
}

function directionColorClass(direction: string): string {
  if (direction === "positive") return "text-success";
  if (direction === "negative") return "text-danger";
  return "text-text-secondary";
}

/**
 * ShapExplanationPanel — renders an ExplainabilityPayload's top-8 SHAP
 * feature contributions (apps/ai-service/src/infrastructure/ml/
 * explainability/shap_explainer.py) as a ranked bar list, plus the
 * human-readable reasoning string the Decision Engine already composes.
 * Every Recommendation carries this — Document 4 §10.9's requirement
 * that every AI recommendation include feature importance + model
 * contribution + explanation + confidence + reasoning.
 */
export function ShapExplanationPanel({ explainability }: ShapExplanationPanelProps) {
  const maxAbsValue = Math.max(
    ...explainability.top_contributions.map((c) => Math.abs(c.value)),
    0.0001
  );

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-semibold text-text-primary">Why this recommendation?</h3>
        <p className="mt-1 text-sm text-text-secondary">{explainability.reasoning}</p>
      </div>

      <ul className="flex flex-col gap-2" aria-label="Feature contributions">
        {explainability.top_contributions.map((contribution) => {
          const widthPct = (Math.abs(contribution.value) / maxAbsValue) * 100;
          return (
            <li key={contribution.name} className="flex items-center gap-3 text-sm">
              <span className="w-32 truncate text-text-secondary" title={contribution.name}>
                {contribution.name}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-primary-100">
                <div
                  className={`h-full rounded-full ${
                    contribution.direction === "negative" ? "bg-danger" : "bg-primary"
                  }`}
                  style={{ width: `${widthPct}%` }}
                />
              </div>
              <span className={`w-16 text-right font-medium ${directionColorClass(contribution.direction)}`}>
                {contribution.value.toFixed(3)}
              </span>
            </li>
          );
        })}
      </ul>

      <p className="text-xs text-text-secondary">
        Method: {explainability.method} · Base value: {explainability.base_value.toFixed(3)}
      </p>
    </Card>
  );
}
