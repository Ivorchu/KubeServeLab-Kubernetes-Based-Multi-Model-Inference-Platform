from typing import Any

from . import config


def route_job(model: str, input: Any) -> str:
    """Return the target model queue for this job.

    If model is "auto", inspect the input to pick the best model.
    Raises ValueError for unknown model names.
    """
    if model != "auto":
        if model not in config.SUPPORTED_MODELS:
            raise ValueError(f"Unknown model '{model}'. Supported: {config.SUPPORTED_MODELS}")
        return model

    return _auto_route(input)


def _auto_route(input: Any) -> str:
    if isinstance(input, dict):
        if "image" in input or "image_url" in input:
            return "image-small"
        text = str(input.get("text") or input.get("prompt") or "")
    else:
        text = str(input)

    if len(text) >= config.TEXT_LARGE_THRESHOLD:
        return "text-large"
    return "text-small"
