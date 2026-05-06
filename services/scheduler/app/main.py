import signal
import time

import redis

from shared.logging import get_logger
from shared.protocol import (
    INCOMING_QUEUE,
    InferenceJob,
    InferenceResult,
    JobStatus,
    job_queue_key,
    result_key,
)

from . import config
from .routing import route_job

logger = get_logger("scheduler.main")

_running = True


def _handle_shutdown(signum, frame):
    global _running
    logger.info("shutdown signal received")
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    r = redis.from_url(config.REDIS_URL, decode_responses=True)
    logger.info("scheduler started, listening on %s", INCOMING_QUEUE)

    while _running:
        item = r.brpop(INCOMING_QUEUE, timeout=config.POLL_TIMEOUT)
        if item is None:
            continue

        _, raw = item
        job = InferenceJob.from_json(raw)
        logger.info("received job=%s model=%s", job.request_id, job.model)

        try:
            target = route_job(job.model, job.input)
        except ValueError as exc:
            logger.warning("routing failed job=%s: %s", job.request_id, exc)
            _write_error(r, job, str(exc))
            continue

        # If "auto" was resolved to a real model, update the job before forwarding
        if job.model != target:
            job = InferenceJob(
                request_id=job.request_id,
                model=target,
                input=job.input,
                created_at=job.created_at,
            )

        dest = job_queue_key(target)
        r.lpush(dest, job.to_json())
        logger.info("routed job=%s → %s", job.request_id, dest)

    logger.info("scheduler shut down cleanly")


def _write_error(r: redis.Redis, job: InferenceJob, error: str) -> None:
    result = InferenceResult(
        request_id=job.request_id,
        model=job.model,
        prediction=None,
        latency_ms=0.0,
        status=JobStatus.FAILED,
        error=error,
    )
    r.setex(result_key(job.request_id), config.POLL_TIMEOUT * 300, result.to_json())


if __name__ == "__main__":
    main()
