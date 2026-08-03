"""Pydantic request DTOs for the AI proxy router — Phase 8. Response
bodies are deliberately forwarded from ai-service unmodified (see
ai_service_client.py's module docstring for why no parallel response DTO
set exists here); only REQUEST bodies get their own Pydantic models, since
those are what FastAPI needs to validate and generate an OpenAPI request
schema for.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    news_texts: list[str] | None = None
    lookback_days: int = Field(default=400, ge=30, le=2000)


class SentimentAnalysisRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    texts: list[str] = Field(..., min_length=1)


class PortfolioHoldingRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity: float = Field(..., gt=0)


class PortfolioRecommendationRequest(BaseModel):
    holdings: list[PortfolioHoldingRequest] = Field(..., min_length=1)
    lookback_days: int = Field(default=400, ge=30, le=2000)


class TrainModelRequest(BaseModel):
    family: str = Field(..., min_length=1, max_length=20)
    symbol: str = Field(..., min_length=1, max_length=20)
    lookback_days: int = Field(default=400, ge=30, le=2000)


class PortfolioIntelligenceHoldingRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity: float = Field(..., gt=0)
    market_value: float = Field(..., gt=0)
    sector: str | None = None


class PortfolioIntelligenceRequest(BaseModel):
    holdings: list[PortfolioIntelligenceHoldingRequest] = Field(..., min_length=1)
    lookback_days: int = Field(default=400, ge=30, le=2000)


class MonteCarloRequest(BaseModel):
    holdings: list[PortfolioIntelligenceHoldingRequest] = Field(..., min_length=1)
    num_runs: int = Field(..., description="Must be one of 100, 500, 1000, 5000")
    horizon_days: int = Field(default=252, ge=1, le=2520)
    lookback_days: int = Field(default=400, ge=30, le=2000)
