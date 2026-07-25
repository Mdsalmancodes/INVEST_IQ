"use client";

import { Card } from "@investiq/ui";

import type { MemberSignalResponse } from "../../../lib/ai-api";

export interface PredictionChartProps {
  memberSignals: MemberSignalResponse[];
}

function signalColorClass(signal: number): string {
  if (signal > 0.05) return "bg-success";
  if (signal < -0.05) return "bg-danger";
  return "bg-warning";
}

/**
 * PredictionChart — visualizes each of the 6 model families' weighted
 * vote signal (in [-1, 1], where positive = bullish / negative =
 * bearish) alongside its own confidence and ensemble weight, matching
 * DecisionEngine's _combine_signals() weighted-voting design (Document
 * 4 §10.4). Distinct from ForecastChart, which shows LSTM/ARIMA/
 * Prophet's actual price-forecast curves — this shows how all 6 models
 * "voted" in the ensemble that produced the Recommendation.
 */
export function PredictionChart({ memberSignals }: PredictionChartProps) {
  if (memberSignals.length === 0) {
    return (
      <Card className="flex h-40 items-center justify-center text-sm text-text-secondary">
        No model signals available for this symbol.
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-text-primary">Model Ensemble Signals</h3>
      <ul className="flex flex-col gap-3">
        {memberSignals.map((signal) => {
          const widthPct = Math.min(100, Math.abs(signal.signal) * 100);
          const isPositive = signal.signal >= 0;
          return (
            <li key={signal.model_family} className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-xs text-text-secondary">
                <span className="font-medium text-text-primary">
                  {signal.model_family.toUpperCase()}
                </span>
                <span>
                  weight {Math.round(signal.weight * 100)}% · confidence{" "}
                  {Math.round(signal.confidence * 100)}%
                </span>
              </div>
              <div className="relative h-2 w-full overflow-hidden rounded-full bg-primary-100">
                <div
                  className={`absolute h-full rounded-full ${signalColorClass(signal.signal)}`}
                  style={{
                    width: `${widthPct / 2}%`,
                    left: isPositive ? "50%" : `${50 - widthPct / 2}%`,
                  }}
                />
                <div className="absolute left-1/2 h-full w-px bg-primary-200" />
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
