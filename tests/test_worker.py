import time
from unittest.mock import MagicMock, patch

import pytest

import services.worker.app.models as worker_models
from services.worker.app.inference import run_inference
from services.worker.app.models import DEFAULT_MODEL, MODEL_REGISTRY
from shared.protocol import InferenceJob, JobStatus


def _make_job(model: str = "text-small", input_text: str = "hello world") -> InferenceJob:
    return InferenceJob(
        request_id="test-request-id",
        model=model,
        input=input_text,
        created_at=time.time(),
    )


@pytest.fixture
def mock_sentiment_pipeline():
    """
    Patch the DistilBERT pipeline loader so tests never trigger a model download.
    Resets the module-level cache before and after each test.
    """
    saved = worker_models._sentiment_pipeline
    worker_models._sentiment_pipeline = None
    mock_pipe = MagicMock(return_value=[{"label": "POSITIVE", "score": 0.9998}])
    with patch("services.worker.app.models._load_sentiment_pipeline", return_value=mock_pipe):
        yield mock_pipe
    worker_models._sentiment_pipeline = saved


# ── Stub models ────────────────────────────────────────────────────────────────

def test_inference_text_small():
    result = run_inference(_make_job("text-small", "this film is great"))
    assert result.status == JobStatus.DONE
    assert result.prediction is not None
    assert "label" in result.prediction
    assert "confidence" in result.prediction
    assert result.latency_ms > 0


def test_inference_text_large():
    result = run_inference(_make_job("text-large", "a long and detailed review"))
    assert result.status == JobStatus.DONE
    assert result.prediction["label"] in ["positive", "negative", "neutral", "mixed"]


def test_inference_image_small():
    result = run_inference(_make_job("image-small", "base64_image_data"))
    assert result.status == JobStatus.DONE
    assert result.prediction["label"] in ["cat", "dog", "bird", "car"]


def test_inference_unknown_model_falls_back():
    result = run_inference(_make_job("nonexistent-model", "test"))
    assert result.status == JobStatus.DONE  # falls back to DEFAULT_MODEL


# ── text-sentiment (real DistilBERT, always mocked in tests) ──────────────────

def test_text_sentiment_in_registry():
    assert "text-sentiment" in MODEL_REGISTRY


def test_inference_text_sentiment_positive(mock_sentiment_pipeline):
    mock_sentiment_pipeline.return_value = [{"label": "POSITIVE", "score": 0.9998}]
    result = run_inference(_make_job("text-sentiment", "this platform is incredibly well-built"))
    assert result.status == JobStatus.DONE
    assert result.prediction["label"] == "POSITIVE"
    assert 0.0 <= result.prediction["score"] <= 1.0
    assert result.latency_ms >= 0


def test_inference_text_sentiment_negative(mock_sentiment_pipeline):
    mock_sentiment_pipeline.return_value = [{"label": "NEGATIVE", "score": 0.9921}]
    result = run_inference(_make_job("text-sentiment", "terrible experience, would not recommend"))
    assert result.status == JobStatus.DONE
    assert result.prediction["label"] == "NEGATIVE"
    assert result.prediction["score"] > 0.5


def test_inference_text_sentiment_truncates_long_input(mock_sentiment_pipeline):
    long_input = "word " * 1000  # well over the 512-token limit
    result = run_inference(_make_job("text-sentiment", long_input))
    assert result.status == JobStatus.DONE
    # pipeline should be called with truncation=True, max_length=512
    mock_sentiment_pipeline.assert_called_once_with(long_input, truncation=True, max_length=512)


def test_inference_text_sentiment_stub_fallback():
    """When transformers is not installed the function degrades to a random stub."""
    saved = worker_models._sentiment_pipeline
    worker_models._sentiment_pipeline = None
    try:
        with patch(
            "services.worker.app.models._load_sentiment_pipeline",
            side_effect=ImportError("No module named 'transformers'"),
        ):
            result = run_inference(_make_job("text-sentiment", "any text"))
        assert result.status == JobStatus.DONE
        assert result.prediction["label"] in ("POSITIVE", "NEGATIVE")
        assert "score" in result.prediction
    finally:
        worker_models._sentiment_pipeline = saved


# ── Cross-cutting ──────────────────────────────────────────────────────────────

def test_all_registered_models(mock_sentiment_pipeline):
    """Every model in the registry should return a DONE result (pipeline mocked)."""
    for model_name in MODEL_REGISTRY:
        result = run_inference(_make_job(model_name, "test input"))
        assert result.status == JobStatus.DONE, f"{model_name} returned {result.status}"
        assert result.request_id == "test-request-id"


def test_result_request_id_preserved():
    job = _make_job("text-small", "testing")
    job.request_id = "custom-id-xyz"
    result = run_inference(job)
    assert result.request_id == "custom-id-xyz"
