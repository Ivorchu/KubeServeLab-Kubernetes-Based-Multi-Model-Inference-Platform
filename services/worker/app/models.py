"""
Model registry — maps model names to inference callables.
Stub models simulate latency for infrastructure testing.
text-sentiment uses a real DistilBERT pipeline (lazy-loaded on first call).
"""
import random
import time
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Stub models
# ---------------------------------------------------------------------------

def _fake_text_classifier(text: str, labels: list[str]) -> dict:
    # Simulate processing proportional to text length, capped at 100 ms
    time.sleep(min(len(str(text)) * 0.0001, 0.1))
    return {
        "label": random.choice(labels),
        "confidence": round(random.uniform(0.65, 0.99), 4),
    }


def text_small(input: Any) -> Any:
    return _fake_text_classifier(str(input), ["positive", "negative", "neutral"])


def text_large(input: Any) -> Any:
    time.sleep(0.05)  # heavier model
    return _fake_text_classifier(
        str(input), ["positive", "negative", "neutral", "mixed"]
    )


def image_small(input: Any) -> Any:
    time.sleep(0.02)
    return {
        "label": random.choice(["cat", "dog", "bird", "car"]),
        "confidence": round(random.uniform(0.7, 0.99), 4),
    }


# ---------------------------------------------------------------------------
# Real model: DistilBERT sentiment (distilbert-base-uncased-finetuned-sst-2-english)
# Lazy-loaded on first call so startup is instant.
# Falls back to stub if transformers/torch are not installed.
# ---------------------------------------------------------------------------

_sentiment_pipeline = None


def _load_sentiment_pipeline():
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        from transformers import pipeline
        _sentiment_pipeline = pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
            device=-1,  # CPU
        )
    return _sentiment_pipeline


def text_sentiment(input: Any) -> dict:
    """
    Real DistilBERT sentiment classifier.
    Returns {"label": "POSITIVE"|"NEGATIVE", "score": float}.
    Falls back to a stub if transformers is unavailable.
    """
    try:
        pipe = _load_sentiment_pipeline()
        result = pipe(str(input), truncation=True, max_length=512)[0]
        return {"label": result["label"], "score": round(result["score"], 4)}
    except ImportError:
        # transformers not installed — degrade gracefully
        time.sleep(0.05)
        return {
            "label": random.choice(["POSITIVE", "NEGATIVE"]),
            "score": round(random.uniform(0.75, 0.99), 4),
            "note": "stub (transformers not installed)",
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

MODEL_REGISTRY: dict[str, Callable] = {
    "text-small": text_small,
    "text-large": text_large,
    "image-small": image_small,
    "text-sentiment": text_sentiment,
}

DEFAULT_MODEL = "text-small"
