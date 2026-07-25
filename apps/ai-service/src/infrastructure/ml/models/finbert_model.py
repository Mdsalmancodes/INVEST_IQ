"""FinBERT sentiment model — Document 4 §10.3's FinBERT scoring step:
"domain-specific BERT fine-tuned on financial text... produces positive/
negative/neutral + confidence." Per the founder's Phase 7 instruction:
analyze financial news, company news, Reddit, market sentiment; output
positive/negative/neutral + confidence score.

Uses `ProsusAI/finbert` (confirmed working in this environment — see
docs/phase-7/known-issues.md for the disclosed one-time model-download
network dependency this implies)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.domain.ml.value_objects import SentimentLabel

_MODEL_NAME = "ProsusAI/finbert"

_LABEL_MAP: dict[str, SentimentLabel] = {
    "positive": "positive",
    "negative": "negative",
    "neutral": "neutral",
}


@dataclass(frozen=True, slots=True)
class SentimentResult:
    label: SentimentLabel
    confidence: float
    source_text: str


@lru_cache(maxsize=1)
def _get_pipeline() -> Any:
    """Lazily constructs the transformers pipeline — expensive (loads a
    real pretrained model into memory), so this is built once per process
    and reused, matching ProphetModel's `is_available()` lru_cache
    pattern for a similarly expensive one-time check."""
    from transformers import pipeline

    # "text-classification" is the canonical task name (the transformers
    # stub's Literal overload doesn't recognize the deprecated
    # "sentiment-analysis" alias, though both resolve identically at
    # runtime) — using it here keeps this call statically type-checked
    # rather than silently falling through to the untyped fallback overload.
    return pipeline("text-classification", model=_MODEL_NAME)


class FinBertModel:
    """Wraps the `ProsusAI/finbert` transformers pipeline for financial
    text sentiment classification — analyzing news headlines, company
    news, and social-media text (Reddit) per the founder's instruction.
    Stateless beyond the lazily-loaded, cached pipeline — there is no
    train()/save()/load() here (unlike the 5 other model families) since
    FinBERT is used as a pretrained inference-only model, matching
    Document 4 §10.3's description of FinBERT as an off-the-shelf
    domain-specific classifier, not something this phase fine-tunes."""

    def analyze(self, text: str) -> SentimentResult:
        if not text or not text.strip():
            raise ValueError("FinBertModel.analyze() requires non-empty text")

        pipeline_fn = _get_pipeline()
        raw_result = pipeline_fn(text)[0]
        label = _LABEL_MAP.get(raw_result["label"].lower(), "neutral")
        confidence = float(raw_result["score"])
        return SentimentResult(label=label, confidence=confidence, source_text=text)

    def analyze_batch(self, texts: list[str]) -> list[SentimentResult]:
        """Batch analysis for multiple news items — Document 4 §10.3's
        ingestion pipeline processes many articles per symbol; this avoids
        reloading the pipeline per-item (already handled by the lru_cache)
        while also letting transformers batch the actual tensor inference
        for throughput."""
        non_empty_texts = [t for t in texts if t and t.strip()]
        if not non_empty_texts:
            return []

        pipeline_fn = _get_pipeline()
        raw_results = pipeline_fn(non_empty_texts)
        return [
            SentimentResult(
                label=_LABEL_MAP.get(raw["label"].lower(), "neutral"),
                confidence=float(raw["score"]),
                source_text=text,
            )
            for text, raw in zip(non_empty_texts, raw_results, strict=True)
        ]
