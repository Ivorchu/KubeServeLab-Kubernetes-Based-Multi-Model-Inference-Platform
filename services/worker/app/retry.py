import time

import redis

from shared.protocol import RETRY_QUEUE, InferenceJob


def backoff_delay(retry_count: int, base_ms: int) -> float:
    """Exponential backoff in seconds: base_ms * 2^retry_count."""
    return (base_ms * (2 ** retry_count)) / 1000.0


def enqueue_retry(r: redis.Redis, job: InferenceJob, base_ms: int) -> None:
    """Push a failed job onto the retry sorted set with a backoff score."""
    delay = backoff_delay(job.retry_count, base_ms)
    score = time.time() + delay
    retried = InferenceJob(
        request_id=job.request_id,
        model=job.model,
        input=job.input,
        created_at=job.created_at,
        retry_count=job.retry_count + 1,
    )
    r.zadd(RETRY_QUEUE, {retried.to_json(): score})
