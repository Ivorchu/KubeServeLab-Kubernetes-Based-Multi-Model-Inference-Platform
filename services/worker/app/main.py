import signal

import redis
from prometheus_client import start_http_server

from shared.logging import get_logger
from shared.protocol import InferenceJob, JobStatus, job_queue_key, result_key

from . import config
from .inference import run_inference
from .metrics import INFERENCE_LATENCY, JOBS_PROCESSED
from .retry import enqueue_retry

logger = get_logger("worker.main")

_running = True


def _handle_shutdown(signum, frame):
    global _running
    logger.info("shutdown signal received")
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    start_http_server(config.METRICS_PORT)
    logger.info("worker=%s started, metrics on :%d", config.WORKER_ID, config.METRICS_PORT)

    redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
    queue_keys = [job_queue_key(m) for m in config.SUPPORTED_MODELS]
    logger.info("polling queues: %s", queue_keys)

    while _running:
        # BRPOP blocks until a job arrives or poll_timeout seconds elapse
        item = redis_client.brpop(queue_keys, timeout=config.POLL_TIMEOUT)
        if item is None:
            continue

        _, raw_job = item
        job = InferenceJob.from_json(raw_job)
        logger.info("processing job=%s model=%s", job.request_id, job.model)

        result = run_inference(job)

        JOBS_PROCESSED.labels(model=job.model, status=result.status.value).inc()
        INFERENCE_LATENCY.labels(model=job.model).observe(result.latency_ms / 1000)

        if result.status == JobStatus.FAILED and job.retry_count < config.MAX_RETRIES:
            enqueue_retry(redis_client, job, config.RETRY_BASE_DELAY_MS)
            logger.info(
                "retry scheduled job=%s attempt=%d/%d",
                job.request_id, job.retry_count + 1, config.MAX_RETRIES,
            )
        else:
            redis_client.setex(result_key(job.request_id), config.RESULT_TTL, result.to_json())

    logger.info("worker shut down cleanly")


if __name__ == "__main__":
    main()
