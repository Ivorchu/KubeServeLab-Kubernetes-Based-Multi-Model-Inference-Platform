import time

import pytest

from shared.protocol import InferenceJob, JobStatus
from services.worker.app.inference import run_inference
from services.worker.app.models import MODEL_REGISTRY, DEFAULT_MODEL


def _make_job(model: str = "text-small", input_text: str = "hello world") -> InferenceJob:
    return InferenceJob(
        request_id="test-request-id",
        model=model,
        input=input_text,
        created_at=time.time(),
    )


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


def test_all_registered_models():
    for model_name in MODEL_REGISTRY:
        result = run_inference(_make_job(model_name, "test input"))
        assert result.status == JobStatus.DONE
        assert result.request_id == "test-request-id"


def test_result_request_id_preserved():
    job = _make_job("text-small", "testing")
    job.request_id = "custom-id-xyz"
    result = run_inference(job)
    assert result.request_id == "custom-id-xyz"
