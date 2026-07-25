"""Unit tests for FinBertModel. Uses the REAL `ProsusAI/finbert`
transformers pipeline (confirmed working in this environment, network
access to Hugging Face Hub required for the first model download —
cached locally afterward). Not mocked, matching this codebase's
established convention of testing real model behavior wherever the
environment supports it (see e.g. test_prophet_model.py).
"""

from __future__ import annotations

import pytest

from src.infrastructure.ml.models.finbert_model import FinBertModel


class TestFinBertAnalyze:
    def test_rejects_empty_text(self) -> None:
        model = FinBertModel()
        with pytest.raises(ValueError, match="non-empty text"):
            model.analyze("")

    def test_rejects_whitespace_only_text(self) -> None:
        model = FinBertModel()
        with pytest.raises(ValueError, match="non-empty text"):
            model.analyze("   ")

    def test_classifies_positive_financial_news(self) -> None:
        model = FinBertModel()
        result = model.analyze("The company reported record profits and strong revenue growth.")
        assert result.label == "positive"
        assert 0.0 <= result.confidence <= 1.0

    def test_classifies_negative_financial_news(self) -> None:
        model = FinBertModel()
        result = model.analyze(
            "The company reported a massive loss and is planning significant layoffs."
        )
        assert result.label == "negative"
        assert 0.0 <= result.confidence <= 1.0

    def test_preserves_source_text(self) -> None:
        model = FinBertModel()
        text = "Shares remained flat in quiet trading."
        result = model.analyze(text)
        assert result.source_text == text


class TestFinBertAnalyzeBatch:
    def test_returns_empty_list_for_empty_input(self) -> None:
        model = FinBertModel()
        assert model.analyze_batch([]) == []

    def test_filters_out_empty_strings(self) -> None:
        model = FinBertModel()
        results = model.analyze_batch(["", "  ", "Strong quarterly earnings beat estimates."])
        assert len(results) == 1

    def test_analyzes_multiple_texts(self) -> None:
        model = FinBertModel()
        texts = [
            "The company reported record profits and strong revenue growth.",
            "The company reported a massive loss and is planning significant layoffs.",
        ]
        results = model.analyze_batch(texts)
        assert len(results) == 2
        assert results[0].label == "positive"
        assert results[1].label == "negative"
