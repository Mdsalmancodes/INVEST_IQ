"""
INVEST IQ - Real FinBERT inference E2E test.

FinBERT is a pretrained inference-only model.

Unlike:
    LSTM
    ARIMA
    Prophet
    Random Forest
    XGBoost

FinBERT is NOT trained by INVEST IQ.

This test validates real pretrained FinBERT inference.
"""

from __future__ import annotations

import pytest

from src.infrastructure.ml.models.finbert_model import (
    FinBertModel,
    SentimentResult,
)


pytestmark = pytest.mark.slow


FINANCIAL_TEXTS = [
    "Apple reported strong quarterly earnings and revenue growth.",
    "The company faces serious losses and declining demand.",
    "The company announced its quarterly results today.",
]


def test_finbert_real_inference_end_to_end() -> None:

    print()
    print("=" * 78)
    print("INVEST IQ - REAL FINBERT INFERENCE E2E TEST")
    print("=" * 78)

    # ========================================================================
    # 1. MODEL CREATION
    # ========================================================================

    print()
    print("=" * 78)
    print("1. FINBERT MODEL")
    print("=" * 78)

    model = FinBertModel()

    assert isinstance(model, FinBertModel)

    print("✅ FinBertModel created.")

    # ========================================================================
    # 2. DEVICE
    # ========================================================================

    print()
    print("=" * 78)
    print("2. INFERENCE DEVICE")
    print("=" * 78)

    device = model.device()

    assert isinstance(device, str)
    assert device

    print(f"Device: {device}")
    print("✅ FinBERT device detected.")

    # ========================================================================
    # 3. MODEL AVAILABILITY
    # ========================================================================

    print()
    print("=" * 78)
    print("3. REAL FINBERT MODEL AVAILABILITY")
    print("=" * 78)

    assert model.is_available() is True

    print("✅ Real pretrained FinBERT is available.")

    # ========================================================================
    # 4. INPUT DATA
    # ========================================================================

    print()
    print("=" * 78)
    print("4. FINANCIAL TEXT INPUT")
    print("=" * 78)

    assert len(FINANCIAL_TEXTS) == 3

    for index, text in enumerate(
        FINANCIAL_TEXTS,
        start=1,
    ):
        print(f"{index:02d}. {text}")

    # ========================================================================
    # 5. REAL INFERENCE
    # ========================================================================

    print()
    print("=" * 78)
    print("5. REAL FINBERT INFERENCE")
    print("=" * 78)

    results = model.analyze_batch(
        FINANCIAL_TEXTS
    )

    assert results
    assert len(results) == len(FINANCIAL_TEXTS)

    print(
        f"✅ Received {len(results)} sentiment results."
    )

    # ========================================================================
    # 6. RESULT VALIDATION
    # ========================================================================

    print()
    print("=" * 78)
    print("6. SENTIMENT RESULT VALIDATION")
    print("=" * 78)

    valid_labels = {
        "positive",
        "neutral",
        "negative",
    }

    for index, result in enumerate(
        results,
        start=1,
    ):

        assert isinstance(
            result,
            SentimentResult,
        )

        assert result.label in valid_labels

        assert (
            0.0
            <= result.confidence
            <= 1.0
        )

        assert result.source_text

        print(
            f"{index:02d}. "
            f"label={result.label} | "
            f"confidence={result.confidence:.6f}"
        )

    # ========================================================================
    # 7. SENTIMENT COVERAGE
    # ========================================================================

    print()
    print("=" * 78)
    print("7. SENTIMENT COVERAGE")
    print("=" * 78)

    labels = {
        result.label
        for result in results
    }

    print(
        "Detected labels:",
        sorted(labels),
    )

    assert "positive" in labels
    assert "negative" in labels
    assert "neutral" in labels

    print(
        "✅ Positive sentiment detected."
    )

    print(
        "✅ Negative sentiment detected."
    )

    print(
        "✅ Neutral sentiment detected."
    )

    # ========================================================================
    # 8. FINAL PIPELINE
    # ========================================================================

    print()
    print("=" * 78)
    print("8. FINAL FINBERT PIPELINE")
    print("=" * 78)

    print(
        """
REAL FINANCIAL TEXT
        ↓
FinBertModel
        ↓
PRETRAINED FINBERT
        ↓
TOKENIZATION
        ↓
TRANSFORMER INFERENCE
        ↓
POSITIVE / NEUTRAL / NEGATIVE
        ↓
CONFIDENCE SCORE
"""
    )

    print("=" * 78)
    print("🎉 FINBERT REAL INFERENCE E2E TEST PASSED")
    print("=" * 78)

    print("✅ Real pretrained FinBERT used")
    print("✅ Model available")
    print("✅ Financial text processed")
    print("✅ Batch inference completed")
    print("✅ Sentiment labels validated")
    print("✅ Confidence values validated")
    print("✅ Positive sentiment detected")
    print("✅ Negative sentiment detected")
    print("✅ Neutral sentiment detected")

    print("=" * 78)