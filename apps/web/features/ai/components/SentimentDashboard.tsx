"use client";

import { Button, Card } from "@investiq/ui";
import { useState } from "react";

import { useSentimentAnalysis } from "../hooks/useAi";
import { ConfidenceIndicator } from "./ConfidenceIndicator";

export interface SentimentDashboardProps {
  symbol: string;
}

const LABEL_STYLES: Record<string, string> = {
  positive: "text-success",
  negative: "text-danger",
  neutral: "text-text-secondary",
};

/**
 * SentimentDashboard — FinBERT-backed sentiment analysis view (Document
 * 4 §10.3): lets a user paste in news/social text items for a symbol and
 * see both the per-item positive/negative/neutral classification and the
 * volume-weighted aggregate Market Sentiment Score
 * (SentimentScore.aggregate()'s min(1.0, count/10) confidence formula).
 */
export function SentimentDashboard({ symbol }: SentimentDashboardProps) {
  const [textInput, setTextInput] = useState("");
  const { mutate, data, isPending, isError, error } = useSentimentAnalysis();

  const handleAnalyze = () => {
    const texts = textInput
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
    if (texts.length === 0) return;
    mutate({ symbol, texts });
  };

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-semibold text-text-primary">Sentiment Analysis</h3>
        <p className="text-xs text-text-secondary">
          Paste financial news, company news, or social posts (one per line) for {symbol}.
        </p>
      </div>

      <textarea
        value={textInput}
        onChange={(event) => setTextInput(event.target.value)}
        placeholder="e.g. Company reports record quarterly profits and raises full-year guidance."
        rows={4}
        className="w-full rounded-md border border-primary-100 bg-surface p-3 text-sm text-text-primary"
        aria-label="News or social text to analyze"
      />

      <Button
        type="button"
        onClick={handleAnalyze}
        disabled={isPending || textInput.trim().length === 0}
      >
        {isPending ? "Analyzing…" : "Analyze Sentiment"}
      </Button>

      {isError && (
        <p role="alert" className="text-sm text-danger">
          Failed to analyze sentiment{error instanceof Error ? `: ${error.message}` : "."}
        </p>
      )}

      {data && (
        <div className="flex flex-col gap-3 border-t border-primary-100 pt-4">
          <div className="flex items-center justify-between">
            <span
              className={`text-lg font-semibold uppercase ${
                LABEL_STYLES[data.aggregate_label] ?? ""
              }`}
            >
              {data.aggregate_label}
            </span>
            <span className="text-xs text-text-secondary">
              {data.aggregate_article_count} item(s) analyzed
            </span>
          </div>
          <ConfidenceIndicator confidence={data.aggregate_confidence} label="Aggregate Confidence" />

          <ul className="flex flex-col gap-2">
            {data.per_item_scores.map((item, index) => (
              <li key={index} className="rounded-md border border-primary-100 p-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className={`font-medium uppercase ${LABEL_STYLES[item.label] ?? ""}`}>
                    {item.label}
                  </span>
                  <span className="text-xs text-text-secondary">
                    {Math.round(item.confidence * 100)}%
                  </span>
                </div>
                {item.source_text && (
                  <p className="mt-1 text-text-secondary">{item.source_text}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
