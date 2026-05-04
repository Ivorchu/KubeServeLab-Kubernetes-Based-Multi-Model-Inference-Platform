"""
Model registry — maps model names to inference callables.
All implementations here are fake placeholders that simulate latency.
Replace with real model loading (ONNX, PyTorch, etc.) in later phases.
"""
import random
import time
from typing import Any, Callable


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


MODEL_REGISTRY: dict[str, Callable] = {
    "text-small": text_small,
    "text-large": text_large,
    "image-small": image_small,
}

DEFAULT_MODEL = "text-small"
