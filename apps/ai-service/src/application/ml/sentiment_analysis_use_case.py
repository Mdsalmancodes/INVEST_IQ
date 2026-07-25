"""SentimentAnalysisUseCase — backs the dedicated "Sentiment Analysis"
API endpoint. Per the founder's Phase 7 instruction: "Analyze: Financial
News, Company News, Reddit, Market Sentiment. Output: Positive, Negative,
Neutral, Confidence Score." Wraps FinBertModel + Document 4 §10.3's
volume-weighted aggregation (SentimentScore.aggregate()) so a single call
covers both per-item classification and the rolling aggregate a symbol's
"Market Sentiment Score" actually needs.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.ml.entities import SentimentScore
from src.domain.ml.exceptions import InsufficientDataError
from src.domain.ml.value_objects import Confidence
from src.infrastructure.ml.models.finbert_model import FinBertModel


@dataclass(frozen=True, slots=True)
class SentimentAnalysisCommand:
    symbol: str
    texts: list[str]


@dataclass(frozen=True, slots=True)
class SentimentAnalysisResult:
    symbol: str
    per_item_scores: tuple[SentimentScore, ...]
    aggregate_score: SentimentScore


class SentimentAnalysisUseCase:
    def __init__(self, finbert: FinBertModel | None = None) -> None:
        self._finbert = finbert or FinBertModel()

    def execute(self, command: SentimentAnalysisCommand) -> SentimentAnalysisResult:
        if not command.texts:
            raise InsufficientDataError(
                f"SentimentAnalysisUseCase requires at least one text item for "
                f"{command.symbol!r}"
            )

        results = self._finbert.analyze_batch(command.texts)
        if not results:
            raise InsufficientDataError(
                f"No non-empty text items were provided for {command.symbol!r}"
            )

        per_item_scores = tuple(
            SentimentScore.create(
                symbol=command.symbol,
                label=r.label,
                confidence=Confidence(round(r.confidence, 4)),
                source_text=r.source_text,
            )
            for r in results
        )
        aggregate_score = SentimentScore.aggregate(command.symbol, per_item_scores)

        return SentimentAnalysisResult(
            symbol=command.symbol.upper(),
            per_item_scores=per_item_scores,
            aggregate_score=aggregate_score,
        )
