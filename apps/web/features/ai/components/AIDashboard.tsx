"use client";

import { Card } from "@investiq/ui";
import { useState } from "react";

import { useForecast, useRecommendation } from "../hooks/useAi";
import { ForecastChart } from "./ForecastChart";
import { ModelStatus } from "./ModelStatus";
import { PredictionChart } from "./PredictionChart";
import { PredictionHistory } from "./PredictionHistory";
import { RecommendationCard } from "./RecommendationCard";
import { SentimentDashboard } from "./SentimentDashboard";

export interface AIDashboardProps {
  initialSymbol?: string;
}

/**
 * AIDashboard — the Phase 7 AI/ML dashboard's top-level composition,
 * matching WatchlistDashboard's page-level composition pattern
 * (features/watchlist/components/WatchlistDashboard.tsx). Lets a user
 * enter a symbol and see: the Buy/Sell/Hold Recommendation (with
 * confidence + SHAP explainability), the model ensemble signal
 * breakdown, the LSTM/ARIMA/Prophet forecast comparison chart,
 * sentiment analysis, prediction history, and overall model status —
 * covering every founder-required Phase 7 frontend view in one page.
 */
export function AIDashboard({ initialSymbol = "" }: AIDashboardProps) {
  const [symbolInput, setSymbolInput] = useState(initialSymbol);
  const [activeSymbol, setActiveSymbol] = useState(initialSymbol);

  const { data: forecastData, isLoading: isForecastLoading } = useForecast(
    activeSymbol || undefined
  );
  // Shares the same query cache entry RecommendationCard's own
  // useRecommendation(activeSymbol) call already populates — TanStack
  // Query deduplicates identical query keys, so this does not trigger a
  // second network request.
  const { data: recommendationData } = useRecommendation(activeSymbol || undefined);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = symbolInput.trim().toUpperCase();
    if (trimmed.length > 0) setActiveSymbol(trimmed);
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">AI Insights</h1>
      </div>

      <Card>
        <form onSubmit={handleSubmit} className="flex gap-2">
          <label htmlFor="ai-symbol-input" className="sr-only">
            Symbol
          </label>
          <input
            id="ai-symbol-input"
            type="text"
            value={symbolInput}
            onChange={(event) => setSymbolInput(event.target.value)}
            placeholder="Enter a symbol, e.g. AAPL"
            className="flex-1 rounded-md border border-primary-100 bg-surface px-3 py-2 text-sm text-text-primary"
          />
          <button
            type="submit"
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white"
          >
            Analyze
          </button>
        </form>
      </Card>

      {activeSymbol ? (
        <>
          <RecommendationCard symbol={activeSymbol} />

          {recommendationData && (
            <PredictionChart memberSignals={recommendationData.member_signals} />
          )}

          {isForecastLoading && (
            <Card
              role="status"
              aria-live="polite"
              className="flex h-72 items-center justify-center animate-pulse bg-primary-50"
            >
              <span className="sr-only">Loading forecast…</span>
            </Card>
          )}
          {forecastData && <ForecastChart memberForecasts={forecastData.member_forecasts} />}

          <SentimentDashboard symbol={activeSymbol} />

          <PredictionHistory symbol={activeSymbol} />
        </>
      ) : (
        <Card className="flex h-32 items-center justify-center text-sm text-text-secondary">
          Enter a symbol above to see AI-generated recommendations and forecasts.
        </Card>
      )}

      <ModelStatus />
    </div>
  );
}
