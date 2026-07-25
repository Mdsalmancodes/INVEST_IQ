"use client";

import { Card } from "@investiq/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { aiKeys, useRecommendation } from "../hooks/useAi";
import { ConfidenceIndicator } from "./ConfidenceIndicator";
import { ShapExplanationPanel } from "./ShapExplanationPanel";
import { useRealtimeConnection } from "../../realtime/hooks/useRealtimeConnection";

export interface RecommendationCardProps {
  symbol: string;
}

const VERDICT_STYLES: Record<string, string> = {
  buy: "bg-success/10 text-success border-success/40",
  sell: "bg-danger/10 text-danger border-danger/40",
  hold: "bg-warning/10 text-warning border-warning/40",
};

function formatMoney(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

const DATA_QUALITY_LABELS: Record<string, string> = {
  full: "Full ensemble",
  partialEnsemble: "Partial ensemble (some models excluded)",
  insufficientHistory: "Insufficient history",
};

/**
 * RecommendationCard — the Buy/Sell/Hold Recommendation view (Document 4
 * §10.4's Recommendation Synthesis output), combining verdict, overall
 * confidence, price forecast, market sentiment score, and full SHAP
 * explainability in one card. Backs both the "Predict" and "Buy/Sell/
 * Hold Recommendation" founder-required views since they share the same
 * underlying computation (GET /api/v1/ml/recommendation/{symbol}).
 * Initial load via useRecommendation (Phase 8, UNMODIFIED — no
 * refetchInterval on this query, since a full ensemble prediction is
 * too expensive to poll; this component works identically with the
 * WebSocket entirely offline, just without any updates after the
 * initial load).
 *
 * Phase 9 ADDITIVE ENHANCEMENT: subscribes to `ai:{symbol}` over the
 * shared WebSocket connection (AiPredictionStreamingService, Task 6 —
 * re-runs the ensemble every 30s for any symbol a connected client has
 * this topic open for) and replaces the cached recommendation wholesale
 * with each fresh tick — AiPredictionStreamingService publishes the
 * EXACT SAME response body useRecommendation's own queryFn receives
 * from the identical get_recommendation() call, so this is a like-for-
 * like cache replacement, not a partial merge.
 */
export function RecommendationCard({ symbol }: RecommendationCardProps) {
  const { data, isLoading, isError, error } = useRecommendation(symbol);
  const queryClient = useQueryClient();
  const { subscribe } = useRealtimeConnection();

  useEffect(() => {
    return subscribe(`ai:${symbol}`, (envelope) => {
      if (!envelope.data) return;
      queryClient.setQueryData(aiKeys.recommendation(symbol), envelope.data);
    });
  }, [symbol, subscribe, queryClient]);

  if (isLoading) {
    return (
      <Card
        role="status"
        aria-live="polite"
        className="flex h-40 items-center justify-center animate-pulse bg-primary-50"
      >
        <span className="sr-only">Loading recommendation…</span>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
        Failed to load recommendation
        {error instanceof Error ? `: ${error.message}` : "."}
      </Card>
    );
  }

  if (!data) return null;

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-text-secondary">{data.symbol}</p>
            <span
              className={`mt-1 inline-block rounded-md border px-3 py-1 text-lg font-semibold uppercase ${
                VERDICT_STYLES[data.verdict] ?? ""
              }`}
            >
              {data.verdict}
            </span>
          </div>
          <div className="text-right">
            <p className="text-sm text-text-secondary">Price forecast (next day)</p>
            <p className="text-2xl font-semibold text-text-primary">
              {formatMoney(data.price_forecast)}
            </p>
          </div>
        </div>

        <ConfidenceIndicator confidence={data.confidence} label="Overall Confidence" />

        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-text-secondary">7-Day Forecast</p>
            <p className="font-medium text-text-primary">{formatMoney(data.price_forecast_7d)}</p>
          </div>
          <div>
            <p className="text-text-secondary">30-Day Forecast</p>
            <p className="font-medium text-text-primary">
              {formatMoney(data.price_forecast_30d)}
            </p>
          </div>
          <div>
            <p className="text-text-secondary">Market Sentiment</p>
            <p className="font-medium text-text-primary">{data.sentiment_score.toFixed(2)}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-secondary">
          <span>{DATA_QUALITY_LABELS[data.data_quality] ?? data.data_quality}</span>
          <span>Contributing models: {data.contributing_models.join(", ")}</span>
        </div>

        {data.excluded_models.length > 0 && (
          <p className="text-xs text-text-secondary">
            Excluded models: {data.excluded_models.join(", ")}
          </p>
        )}
      </Card>

      <ShapExplanationPanel explainability={data.explainability} />
    </div>
  );
}
