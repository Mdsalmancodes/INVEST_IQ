"""
FinBERT financial-sentiment model for INVEST IQ.

Model
-----
ProsusAI/finbert

Purpose
-------
Classify financial text into:

    positive
    neutral
    negative

and return the model confidence.

Supported sources include:

    - financial news
    - company news
    - market commentary
    - Reddit/social-media text

Important
---------
FinBERT is a pretrained inference-only model in this phase.

It is therefore NOT trained by TrainModelUseCase and does not produce
a persisted model artifact like LSTM, ARIMA, Prophet, Random Forest,
or XGBoost.

The expensive Hugging Face pipeline is loaded lazily and cached for
reuse within the process.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
import torch
from transformers import pipeline

from src.domain.ml.value_objects import SentimentLabel


# ============================================================================
# CONFIGURATION
# ============================================================================

MODEL_NAME = "ProsusAI/finbert"

# FinBERT is based on BERT and therefore uses a 512-token maximum sequence
# length. We deliberately leave a little room below the absolute maximum.
MAX_INPUT_TOKENS = 512

# Number of texts processed by the pipeline at once.
#
# This prevents a very large Reddit/news batch from unnecessarily consuming
# GPU memory.
DEFAULT_BATCH_SIZE = 16

# Pipeline task.
PIPELINE_TASK = "text-classification"


# ============================================================================
# LABEL MAPPING
# ============================================================================

_LABEL_MAP: dict[str, SentimentLabel] = {
    "positive": "positive",
    "neutral": "neutral",
    "negative": "negative",
}


# ============================================================================
# RESULT
# ============================================================================


@dataclass(frozen=True, slots=True)
class SentimentResult:
    """
    Result for one piece of financial text.
    """

    label: SentimentLabel

    confidence: float

    source_text: str


# ============================================================================
# DEVICE
# ============================================================================


def _get_device() -> int:
    """
    Return the Hugging Face pipeline device.

    Hugging Face pipeline expects:

        -1 -> CPU
         0 -> first CUDA GPU

    INVEST IQ therefore automatically uses the RTX 4060 when CUDA is
    available and falls back to CPU otherwise.
    """

    if torch.cuda.is_available():

        return 0

    return -1


# ============================================================================
# PIPELINE
# ============================================================================


@lru_cache(maxsize=1)
def _get_pipeline() -> Any:
    """
    Lazily create and cache the FinBERT inference pipeline.

    The model is downloaded/loaded only once per Python process.

    This is important because loading FinBERT for every article would be
    extremely expensive.
    """

    device = _get_device()

    classifier = pipeline(
        task=PIPELINE_TASK,
        model=MODEL_NAME,
        tokenizer=MODEL_NAME,
        device=device,
    )

    return classifier


# ============================================================================
# RESULT VALIDATION
# ============================================================================


def _normalize_result(
    raw_result: Any,
    source_text: str,
) -> SentimentResult:
    """
    Convert a raw Hugging Face classification result into the domain-level
    SentimentResult.

    This keeps transformer-specific output details outside the application
    layer.
    """

    if not isinstance(
        raw_result,
        dict,
    ):

        raise RuntimeError(
            "FinBERT returned an unexpected result format."
        )

    raw_label = raw_result.get(
        "label"
    )

    raw_score = raw_result.get(
        "score"
    )

    if not isinstance(
        raw_label,
        str,
    ):

        raise RuntimeError(
            "FinBERT response did not contain a valid label."
        )

    try:

        confidence = float(
            raw_score
        )

    except (
        TypeError,
        ValueError,
    ) as exc:

        raise RuntimeError(
            "FinBERT response did not contain "
            "a valid confidence score."
        ) from exc

    label = _LABEL_MAP.get(
        raw_label.strip().lower()
    )

    if label is None:

        # FinBERT should return one of the three expected labels.
        # Treat an unknown label as an integration error instead of silently
        # turning a model failure into neutral sentiment.
        raise RuntimeError(
            f"FinBERT returned unsupported sentiment label: "
            f"{raw_label!r}"
        )

    if not np.isfinite(
        confidence
    ):

        raise RuntimeError(
            "FinBERT returned a non-finite confidence score."
        )

    confidence = max(
        0.0,
        min(
            1.0,
            confidence,
        ),
    )

    return SentimentResult(
        label=label,
        confidence=confidence,
        source_text=source_text,
    )


# ============================================================================
# MODEL
# ============================================================================


class FinBertModel:
    """
    Wrapper around ProsusAI/finbert.

    This class intentionally has no:

        train()
        save()
        load()

    because FinBERT is used as a pretrained inference model in the current
    INVEST IQ architecture.
    """

    # ========================================================================
    # AVAILABILITY
    # ========================================================================

    @staticmethod
    def is_available() -> bool:
        """
        Check whether the FinBERT pipeline can be loaded.

        This performs the real model-loading check.

        Returns:
            True  -> model can be loaded
            False -> dependency/model/network/cache problem
        """

        try:

            _get_pipeline()

            return True

        except Exception:

            return False

    # ========================================================================
    # DEVICE
    # ========================================================================

    @staticmethod
    def device() -> str:
        """
        Return the active inference device.
        """

        if torch.cuda.is_available():

            return torch.cuda.get_device_name(
                0
            )

        return "cpu"

    # ========================================================================
    # SINGLE TEXT
    # ========================================================================

    def analyze(
        self,
        text: str,
    ) -> SentimentResult:
        """
        Analyze one financial text item.
        """

        if not isinstance(
            text,
            str,
        ):

            raise TypeError(
                "FinBertModel.analyze() requires text to be a string."
            )

        cleaned_text = text.strip()

        if not cleaned_text:

            raise ValueError(
                "FinBertModel.analyze() requires non-empty text."
            )

        pipeline_fn = _get_pipeline()

        # inference_mode disables autograd and is preferable for pure
        # inference because FinBERT is never being trained here.
        with torch.inference_mode():

            raw_results = pipeline_fn(
                cleaned_text,
                truncation=True,
                max_length=MAX_INPUT_TOKENS,
            )

        if not raw_results:

            raise RuntimeError(
                "FinBERT returned no sentiment result."
            )

        return _normalize_result(
            raw_results[0],
            cleaned_text,
        )

    # ========================================================================
    # BATCH
    # ========================================================================

    def analyze_batch(
        self,
        texts: list[str],
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> list[SentimentResult]:
        """
        Analyze multiple financial text items.

        Empty/whitespace-only entries are ignored.

        The remaining texts are processed in bounded batches so that a large
        collection of news/Reddit posts does not unnecessarily exhaust GPU
        memory.
        """

        if batch_size <= 0:

            raise ValueError(
                "batch_size must be greater than zero."
            )

        if not texts:

            return []

        cleaned_texts = [
            text.strip()
            for text in texts
            if isinstance(
                text,
                str,
            )
            and text.strip()
        ]

        if not cleaned_texts:

            return []

        pipeline_fn = _get_pipeline()

        results: list[
            SentimentResult
        ] = []

        with torch.inference_mode():

            for start_index in range(
                0,
                len(cleaned_texts),
                batch_size,
            ):

                batch = cleaned_texts[
                    start_index : start_index
                    + batch_size
                ]

                raw_results = pipeline_fn(
                    batch,
                    truncation=True,
                    max_length=MAX_INPUT_TOKENS,
                    batch_size=batch_size,
                )

                if len(
                    raw_results
                ) != len(
                    batch
                ):

                    raise RuntimeError(
                        "FinBERT returned a different number "
                        "of results than input texts."
                    )

                for text, raw_result in zip(
                    batch,
                    raw_results,
                    strict=True,
                ):

                    results.append(
                        _normalize_result(
                            raw_result,
                            text,
                        )
                    )

        return results