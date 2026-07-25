"""PortfolioRecommendationUseCase — backs the "Portfolio Recommendation"
API endpoint. Per the founder's Phase 7 instruction, the Decision Engine
must produce a "Portfolio Recommendation" alongside the per-instrument
BUY/SELL/HOLD verdict.

SCOPE BOUNDARY (disclosed, not silently narrowed — see known-issues.md):
this use case accepts a list of (symbol, quantity) holdings directly as
input parameters, rather than calling core-api's portfolio endpoints
itself. core-api's portfolio endpoints require bearer-token
authentication (unlike Market Data's public endpoints this bounded
context already calls), and ai-service has no user-session/auth concept
of its own. Accepting holdings as direct input keeps ai-service
stateless and decoupled from core-api's auth machinery — the
presentation layer (core-api's BFF-style caller, or a future
authenticated gateway) is responsible for supplying the user's actual
holdings, which it already has access to via its own authenticated
Portfolio module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from src.application.ml.decision_engine import DecisionEngine, DecisionEngineResult
from src.domain.ml.exceptions import InsufficientDataError
from src.domain.ml.repositories import MarketDataRepository
from src.domain.ml.value_objects import Verdict


@dataclass(frozen=True, slots=True)
class PortfolioHolding:
    symbol: str
    quantity: float


@dataclass(frozen=True, slots=True)
class PortfolioRecommendationCommand:
    holdings: list[PortfolioHolding]
    lookback_days: int = 400


@dataclass(frozen=True, slots=True)
class PortfolioRecommendationItem:
    symbol: str
    quantity: float
    decision: DecisionEngineResult


@dataclass(frozen=True, slots=True)
class PortfolioRecommendationResult:
    items: tuple[PortfolioRecommendationItem, ...]
    overall_verdict: Verdict
    overall_sentiment_score: float


class PortfolioRecommendationUseCase:
    def __init__(
        self,
        market_data_repository: MarketDataRepository,
        decision_engine: DecisionEngine | None = None,
    ) -> None:
        self._market_data_repository = market_data_repository
        self._decision_engine = decision_engine or DecisionEngine()

    async def execute(
        self, command: PortfolioRecommendationCommand
    ) -> PortfolioRecommendationResult:
        if not command.holdings:
            raise InsufficientDataError(
                "PortfolioRecommendationUseCase requires at least one holding"
            )

        end = date.today()
        start = end - timedelta(days=command.lookback_days)

        items: list[PortfolioRecommendationItem] = []
        for holding in command.holdings:
            bars = await self._market_data_repository.get_ohlcv_bars(
                holding.symbol, start, end
            )
            if not bars:
                continue
            ohlcv = pd.DataFrame(
                {
                    "open": [b.open for b in bars],
                    "high": [b.high for b in bars],
                    "low": [b.low for b in bars],
                    "close": [b.close for b in bars],
                    "volume": [b.volume for b in bars],
                }
            )
            decision = self._decision_engine.decide(holding.symbol, ohlcv)
            items.append(
                PortfolioRecommendationItem(
                    symbol=holding.symbol.upper(), quantity=holding.quantity, decision=decision
                )
            )

        if not items:
            raise InsufficientDataError(
                "None of the provided holdings had sufficient market data to evaluate"
            )

        overall_verdict = _aggregate_verdict(items)
        overall_sentiment = sum(
            item.decision.recommendation.sentiment_score for item in items
        ) / len(items)

        return PortfolioRecommendationResult(
            items=tuple(items),
            overall_verdict=overall_verdict,
            overall_sentiment_score=round(overall_sentiment, 4),
        )


def _aggregate_verdict(items: list[PortfolioRecommendationItem]) -> Verdict:
    """Quantity-weighted majority vote across holdings' individual
    verdicts — a portfolio-level BUY/SELL/HOLD summary, distinct from
    (but built from) each holding's own DecisionEngine verdict."""
    verdict_weights: dict[Verdict, float] = {"buy": 0.0, "sell": 0.0, "hold": 0.0}
    for item in items:
        verdict_weights[item.decision.recommendation.verdict] += item.quantity
    return max(verdict_weights, key=lambda v: verdict_weights[v])
