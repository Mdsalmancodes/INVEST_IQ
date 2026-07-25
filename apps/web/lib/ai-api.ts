/**
 * Typed API client for AI/ML features — Phase 8: rewired to call
 * core-api's AI proxy (/api/v1/ai/*, src/presentation/routers/
 * ai_proxy_router.py) instead of calling ai-service directly.
 *
 * PHASE 7 → PHASE 8 CHANGE (closing the disclosed Phase 7 gap): this
 * module previously called ai-service's own base URL
 * (NEXT_PUBLIC_AI_SERVICE_BASE_URL) with no authentication at all — see
 * docs/phase-7/known-issues.md's A1/A2 entries. Phase 8 built a proper
 * API Gateway/proxy layer in core-api (src/application/ai_proxy/
 * ai_service_client.py + src/infrastructure/http/ai_service_client.py)
 * specifically so the AI Service is never directly reachable by a
 * browser client — ai-service's own presentation layer now rejects any
 * request lacking the internal-only X-Internal-Service-Token header
 * (src/presentation/internal_auth_middleware.py), a header only
 * core-api's HttpAiServiceClient ever sends. This client therefore now
 * follows lib/portfolio-api.ts's authorizedRequest<T>() convention
 * exactly: every call requires a bearer access token (read from
 * useAuthStore, matching that module's own pattern precisely), and the
 * 4 admin-only endpoints (models/status, train, retrain, delete) are
 * additionally gated server-side by require_role([Role.ADMIN,
 * Role.SUPER_ADMIN]) — a non-admin caller reaching one of those still
 * gets a 403 from core-api even if this client is called directly,
 * matching the disclosed principle that the UI-level RequireRole guard
 * (features/auth/components/RequireRole.tsx) is a UX convenience, not
 * the real authorization boundary.
 */

import { useAuthStore } from "../store/auth-store";
import { ApiError, type ApiErrorPayload } from "./auth-api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

async function authorizedRequest<TResponse>(
  path: string,
  options: RequestInit = {}
): Promise<TResponse> {
  const accessToken = useAuthStore.getState().accessToken;
  if (!accessToken) {
    throw new ApiError("NOT_AUTHENTICATED", "No active session", 401);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...options.headers,
    },
  });

  if (response.status === 204) {
    return undefined as TResponse;
  }

  const body = await response.json();

  if (!response.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : ((body as ApiErrorPayload)?.error?.message ?? "Request failed");
    const code = (body as ApiErrorPayload)?.error?.code ?? "REQUEST_FAILED";
    throw new ApiError(code, detail, response.status);
  }

  return body as TResponse;
}

export interface FeatureContributionResponse {
  name: string;
  value: number;
  direction: string;
}

export interface ExplainabilityResponse {
  top_contributions: FeatureContributionResponse[];
  base_value: number;
  method: string;
  reasoning: string;
}

export interface HorizonPointResponse {
  horizon_days: number;
  predicted_price: number;
  lower_bound: number;
  upper_bound: number;
}

export interface MemberForecastResponse {
  model_family: string;
  points: HorizonPointResponse[];
  confidence: number;
  data_quality: string;
}

export interface MemberSignalResponse {
  model_family: string;
  signal: number;
  confidence: number;
  weight: number;
}

export interface RecommendationResponse {
  symbol: string;
  verdict: "buy" | "sell" | "hold";
  confidence: number;
  price_forecast: number;
  sentiment_score: number;
  data_quality: "full" | "insufficientHistory" | "partialEnsemble";
  contributing_models: string[];
  explainability: ExplainabilityResponse;
  member_signals: MemberSignalResponse[];
  excluded_models: string[];
  price_forecast_7d: number;
  price_forecast_30d: number;
}

export interface PredictPayload {
  symbol: string;
  news_texts?: string[];
  lookback_days?: number;
}

export interface ForecastResponse {
  symbol: string;
  member_forecasts: MemberForecastResponse[];
  excluded_models: string[];
}

export interface SentimentAnalysisPayload {
  symbol: string;
  texts: string[];
}

export interface SentimentItemResponse {
  label: "positive" | "negative" | "neutral";
  confidence: number;
  source_text: string | null;
}

export interface SentimentAnalysisResponse {
  symbol: string;
  per_item_scores: SentimentItemResponse[];
  aggregate_label: "positive" | "negative" | "neutral";
  aggregate_confidence: number;
  aggregate_article_count: number;
}

export interface PortfolioHoldingPayload {
  symbol: string;
  quantity: number;
}

export interface PortfolioRecommendationPayload {
  holdings: PortfolioHoldingPayload[];
  lookback_days?: number;
}

export interface PortfolioRecommendationItemResponse {
  symbol: string;
  quantity: number;
  verdict: "buy" | "sell" | "hold";
  confidence: number;
  price_forecast: number;
}

export interface PortfolioRecommendationResponse {
  items: PortfolioRecommendationItemResponse[];
  overall_verdict: "buy" | "sell" | "hold";
  overall_sentiment_score: number;
}

export interface PredictionRunResponse {
  id: string;
  symbol: string;
  ensemble_price: number;
  ensemble_confidence: number;
  data_quality: string;
  created_at: string;
  actual_price: number | null;
}

export interface PredictionHistoryResponse {
  symbol: string;
  items: PredictionRunResponse[];
}

export interface ModelVersionResponse {
  id: string;
  version_tag: string;
  trained_at: string;
  status: string;
  validation_metrics: Record<string, number>;
  artifact_location: string;
}

export interface ModelFamilyStatusResponse {
  family: string;
  active_version: ModelVersionResponse | null;
  version_count: number;
}

export interface ModelStatusResponse {
  families: ModelFamilyStatusResponse[];
}

export interface TrainModelPayload {
  family: string;
  symbol: string;
  lookback_days?: number;
}

export interface TrainModelResponse {
  model_version: ModelVersionResponse;
  validation_metrics: Record<string, number>;
}

function buildQueryString(params: Record<string, string | number | undefined>): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    searchParams.append(key, String(value));
  }
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export const aiApi = {
  predict: (payload: PredictPayload) =>
    authorizedRequest<RecommendationResponse>("/api/v1/ai/predict", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getRecommendation: (symbol: string) =>
    authorizedRequest<RecommendationResponse>(`/api/v1/ai/recommendation/${symbol}`),

  getForecast: (symbol: string, lookbackDays?: number) =>
    authorizedRequest<ForecastResponse>(
      `/api/v1/ai/forecast/${symbol}${buildQueryString({ lookback_days: lookbackDays })}`
    ),

  analyzeSentiment: (payload: SentimentAnalysisPayload) =>
    authorizedRequest<SentimentAnalysisResponse>("/api/v1/ai/sentiment", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getPortfolioRecommendation: (payload: PortfolioRecommendationPayload) =>
    authorizedRequest<PortfolioRecommendationResponse>("/api/v1/ai/portfolio-recommendation", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getPredictionHistory: (symbol: string, limit?: number) =>
    authorizedRequest<PredictionHistoryResponse>(
      `/api/v1/ai/history/${symbol}${buildQueryString({ limit })}`
    ),

  // --- Admin-only (core-api's require_role([Role.ADMIN, Role.SUPER_ADMIN])
  // gates these 4 server-side; a non-admin caller still gets a 403 from
  // core-api even if this client method is invoked directly) ---

  getModelStatus: () => authorizedRequest<ModelStatusResponse>("/api/v1/ai/models/status"),

  trainModel: (payload: TrainModelPayload) =>
    authorizedRequest<TrainModelResponse>("/api/v1/ai/models/train", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  retrainModel: (payload: TrainModelPayload) =>
    authorizedRequest<TrainModelResponse>("/api/v1/ai/models/retrain", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Phase 8 addition — core-api's DELETE /api/v1/ai/models/{id}, proxying ai-service's Task 3-added DeleteModelUseCase. */
  deleteModel: (modelVersionId: string) =>
    authorizedRequest<undefined>(`/api/v1/ai/models/${modelVersionId}`, {
      method: "DELETE",
    }),
};
