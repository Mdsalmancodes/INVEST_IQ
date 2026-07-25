"""Unit tests for SentimentAnalysisUseCase. Uses the REAL FinBERT model
(confirmed working — see docs/phase-7/known-issues.md), not mocked.
"""

from __future__ import annotations

import pytest

from src.application.ml.sentiment_analysis_use_case import (
    SentimentAnalysisCommand,
    SentimentAnalysisUseCase,
)
from src.domain.ml.exceptions import InsufficientDataError


class TestSentimentAnalysisUseCase:
    def test_raises_when_no_texts_provided(self) -> None:
        use_case = SentimentAnalysisUseCase()
        with pytest.raises(InsufficientDataError, match="at least one text item"):
            use_case.execute(SentimentAnalysisCommand(symbol="AAPL", texts=[]))

    def test_raises_when_only_empty_strings_provided(self) -> None:
        use_case = SentimentAnalysisUseCase()
        with pytest.raises(InsufficientDataError, match="No non-empty text"):
            use_case.execute(SentimentAnalysisCommand(symbol="AAPL", texts=["", "   "]))

    def test_analyzes_positive_and_negative_texts(self) -> None:
        use_case = SentimentAnalysisUseCase()
        result = use_case.execute(
            SentimentAnalysisCommand(
                symbol="aapl",
                texts=[
                    "The company reported record profits and strong revenue growth.",
                    "The company reported a massive loss and is planning layoffs.",
                ],
            )
        )

        assert result.symbol == "AAPL"
        assert len(result.per_item_scores) == 2
        assert result.per_item_scores[0].label == "positive"
        assert result.per_item_scores[1].label == "negative"

    def test_aggregate_score_reflects_article_volume(self) -> None:
        use_case = SentimentAnalysisUseCase()
        result = use_case.execute(
            SentimentAnalysisCommand(
                symbol="AAPL", texts=["Strong quarterly earnings beat estimates."]
            )
        )

        # 1 article / target_volume(10) = 0.1 — honestly low confidence,
        # matching SentimentScore.aggregate()'s documented formula.
        assert result.aggregate_score.confidence.value == pytest.approx(0.1)
        assert result.aggregate_score.article_count == 1
