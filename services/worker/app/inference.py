import time

from shared.logging import get_logger
from shared.protocol import InferenceJob, InferenceResult, JobStatus

from .models import DEFAULT_MODEL, MODEL_REGISTRY

logger = get_logger("worker.inference")


def run_inference(job: InferenceJob) -> InferenceResult:
    start = time.time()
    model_fn = MODEL_REGISTRY.get(job.model) or MODEL_REGISTRY[DEFAULT_MODEL]

    try:
        prediction = model_fn(job.input)
        latency_ms = (time.time() - start) * 1000
        logger.info("job=%s model=%s latency=%.1fms", job.request_id, job.model, latency_ms)
        return InferenceResult(
            request_id=job.request_id,
            model=job.model,
            prediction=prediction,
            latency_ms=round(latency_ms, 2),
            status=JobStatus.DONE,
        )
    except Exception as exc:
        latency_ms = (time.time() - start) * 1000
        logger.error("job=%s failed: %s", job.request_id, exc)
        return InferenceResult(
            request_id=job.request_id,
            model=job.model,
            prediction=None,
            latency_ms=round(latency_ms, 2),
            status=JobStatus.FAILED,
            error=str(exc),
        )
