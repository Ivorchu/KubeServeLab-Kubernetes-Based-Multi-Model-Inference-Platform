import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import redis

from shared.logging import get_logger
from shared.protocol import (
    INCOMING_QUEUE,
    RETRY_QUEUE,
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


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def _start_health_server(port: int) -> None:
    server = HTTPServer(("", port), _HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


def _handle_shutdown(signum, frame):
    global _running
    logger.info("shutdown signal received")
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    _start_health_server(config.HEALTH_PORT)

    r = redis.from_url(config.REDIS_URL, decode_responses=True)
    logger.info("scheduler started, health on :%d, listening on %s", config.HEALTH_PORT, INCOMING_QUEUE)

    while _running:
        _requeue_ready_retries(r)

        item = r.brpop(INCOMING_QUEUE, timeout=config.POLL_TIMEOUT)
        if item is None:
            continue

        _, raw = item
        job = InferenceJob.from_json(raw)
        logger.info("received job=%s model=%s attempt=%d", job.request_id, job.model, job.retry_count)

        try:
            target = route_job(job.model, job.input)
        except ValueError as exc:
            logger.warning("routing failed job=%s: %s", job.request_id, exc)
            _write_error(r, job, str(exc))
            continue

        if job.model != target:
            job = InferenceJob(
                request_id=job.request_id,
                model=target,
                input=job.input,
                created_at=job.created_at,
                retry_count=job.retry_count,
            )

        dest = job_queue_key(target)
        r.lpush(dest, job.to_json())
        logger.info("routed job=%s → %s", job.request_id, dest)

    logger.info("scheduler shut down cleanly")


def _requeue_ready_retries(r: redis.Redis) -> None:
    """Move any retry-queue jobs whose backoff has elapsed back to queue:incoming."""
    now = time.time()
    while True:
        ready = r.zrangebyscore(RETRY_QUEUE, "-inf", now, start=0, num=10)
        if not ready:
            break
        pipe = r.pipeline()
        for raw in ready:
            pipe.zrem(RETRY_QUEUE, raw)
            pipe.lpush(INCOMING_QUEUE, raw)
        pipe.execute()
        for raw in ready:
            job = InferenceJob.from_json(raw)
            logger.info("requeued retry job=%s attempt=%d", job.request_id, job.retry_count)
        if len(ready) < 10:
            break


def _write_error(r: redis.Redis, job: InferenceJob, error: str) -> None:
    result = InferenceResult(
        request_id=job.request_id,
        model=job.model,
        prediction=None,
        latency_ms=0.0,
        status=JobStatus.FAILED,
        error=error,
    )
    r.setex(result_key(job.request_id), config.RESULT_TTL, result.to_json())


if __name__ == "__main__":
    main()
