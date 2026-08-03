"use client";

import { Card } from "@investiq/ui";
import gsap from "gsap";
import { useLayoutEffect, useRef, useState } from "react";

import { MagneticButton } from "../../dashboard-shell/components/MagneticButton";
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
 *
 * Production-polish pass: GSAP powers a staggered reveal of the results
 * section (Recommendation → signals → forecast → sentiment → history)
 * whenever a new symbol is analyzed — this is the one place in the
 * dashboard dense/sequential enough to benefit from GSAP's timeline
 * API over a plain `motion` stagger (every child here is conditionally
 * rendered based on independent async query state, not a static list,
 * so a single gsap.fromTo() on the container's direct children after
 * they mount reveals whichever combination is ready, in order, without
 * needing to coordinate each child's own animation state).
 */
export function AIDashboard({ initialSymbol = "" }: AIDashboardProps) {
  const [symbolInput, setSymbolInput] = useState(initialSymbol);
  const [activeSymbol, setActiveSymbol] = useState(initialSymbol);
  const resultsRef = useRef<HTMLDivElement>(null);

  const { data: forecastData, isLoading: isForecastLoading } = useForecast(
    activeSymbol || undefined
  );
  // Shares the same query cache entry RecommendationCard's own
  // useRecommendation(activeSymbol) call already populates — TanStack
  // Query deduplicates identical query keys, so this does not trigger a
  // second network request.
  const { data: recommendationData } = useRecommendation(activeSymbol || undefined);

  useLayoutEffect(() => {
    if (!activeSymbol || !resultsRef.current) return;
    const children = Array.from(resultsRef.current.children);
    gsap.fromTo(
      children,
      { opacity: 0, y: 16 },
      { opacity: 1, y: 0, duration: 0.5, stagger: 0.08, ease: "power2.out" }
    );
    // Rapid re-submission of a new symbol before the previous tween
    // finishes would otherwise stack overlapping tweens on the same
    // elements (gsap.fromTo doesn't automatically cancel a still-running
    // tween on the same targets) — killing any in-flight tween on these
    // children before this effect's next run/unmount keeps at most one
    // active animation on this container at a time.
    return () => {
      gsap.killTweensOf(children);
    };
  }, [activeSymbol]);

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
          <MagneticButton type="submit">Analyze</MagneticButton>
        </form>
      </Card>

      {activeSymbol ? (
        <div ref={resultsRef} className="flex flex-col gap-6">
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
        </div>
      ) : (
        <Card className="flex h-32 items-center justify-center text-sm text-text-secondary">
          Enter a symbol above to see AI-generated recommendations and forecasts.
        </Card>
      )}

      <ModelStatus />
    </div>
  );
}
