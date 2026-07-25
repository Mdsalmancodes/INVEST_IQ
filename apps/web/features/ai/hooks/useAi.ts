/**
 * TanStack Query hooks for AI/ML features — Phase 8: now calls core-api's
 * authenticated /api/v1/ai/* proxy (lib/ai-api.ts) instead of ai-service
 * directly. Unlike Phase 7, these hooks do NOT need to read useAuthStore
 * themselves — lib/ai-api.ts's authorizedRequest<T>() reads the access
 * token internally, matching lib/portfolio-api.ts's exact established
 * convention (see that module's own docstring).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  aiApi,
  type PortfolioRecommendationPayload,
  type PredictPayload,
  type SentimentAnalysisPayload,
  type TrainModelPayload,
} from "../../../lib/ai-api";

export const aiKeys = {
  recommendation: (symbol: string) => ["ai", "recommendation", symbol] as const,
  forecast: (symbol: string, lookbackDays?: number) =>
    ["ai", "forecast", symbol, lookbackDays] as const,
  history: (symbol: string, limit?: number) => ["ai", "history", symbol, limit] as const,
  modelStatus: () => ["ai", "model-status"] as const,
};

/** Buy/Sell/Hold Recommendation — GET variant, matching the backend's
 * disclosed design that /recommendation/{symbol} and POST /predict run
 * the identical Hybrid Decision Engine computation
 * (apps/ai-service/src/application/ml/predict_use_case.py's docstring). */
export function useRecommendation(symbol: string | undefined) {
  return useQuery({
    queryKey: aiKeys.recommendation(symbol ?? ""),
    queryFn: () => aiApi.getRecommendation(symbol as string),
    enabled: symbol !== undefined && symbol.length > 0,
  });
}

/** POST /predict — used when the caller needs to pass news_texts for
 * FinBERT sentiment inclusion, or a custom lookback window; otherwise
 * prefer useRecommendation's simpler GET form. */
export function usePredict() {
  return useMutation({
    mutationFn: (payload: PredictPayload) => aiApi.predict(payload),
  });
}

export function useForecast(symbol: string | undefined, lookbackDays?: number) {
  return useQuery({
    queryKey: aiKeys.forecast(symbol ?? "", lookbackDays),
    queryFn: () => aiApi.getForecast(symbol as string, lookbackDays),
    enabled: symbol !== undefined && symbol.length > 0,
  });
}

export function useSentimentAnalysis() {
  return useMutation({
    mutationFn: (payload: SentimentAnalysisPayload) => aiApi.analyzeSentiment(payload),
  });
}

export function usePortfolioRecommendation() {
  return useMutation({
    mutationFn: (payload: PortfolioRecommendationPayload) =>
      aiApi.getPortfolioRecommendation(payload),
  });
}

export function usePredictionHistory(symbol: string | undefined, limit?: number) {
  return useQuery({
    queryKey: aiKeys.history(symbol ?? "", limit),
    queryFn: () => aiApi.getPredictionHistory(symbol as string, limit),
    enabled: symbol !== undefined && symbol.length > 0,
  });
}

export function useModelStatus() {
  return useQuery({
    queryKey: aiKeys.modelStatus(),
    queryFn: () => aiApi.getModelStatus(),
    // Model versions change infrequently (only after a train/retrain
    // call) — a 60s staleTime avoids needlessly re-fetching on every
    // dashboard remount while still catching a recent retrain reasonably
    // soon, matching useMarketStatus's staleTime convention.
    staleTime: 60_000,
  });
}

export function useTrainModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TrainModelPayload) => aiApi.trainModel(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiKeys.modelStatus() });
    },
  });
}

export function useRetrainModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TrainModelPayload) => aiApi.retrainModel(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiKeys.modelStatus() });
    },
  });
}

/** Phase 8 addition — admin-only model deletion (core-api's require_role-gated DELETE /api/v1/ai/models/{id}). */
export function useDeleteModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (modelVersionId: string) => aiApi.deleteModel(modelVersionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiKeys.modelStatus() });
    },
  });
}
