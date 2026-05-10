import asyncio
import time
from typing import AsyncGenerator, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger
from shared.protocol import (
    INCOMING_QUEUE,
    InferenceJob,
    InferenceResult,
    JobStatus,
    generate_request_id,
    result_key,
)

from . import config
from .circuit_breaker import CircuitBreaker
from .database import get_db
from .db_models import RequestLog
from .metrics import CB_OPEN, QUEUE_LENGTH, REQUEST_COUNT, REQUEST_LATENCY, TIMEOUT_COUNT
from .schemas import HealthResponse, PredictRequest, PredictResponse, StatusResponse

router = APIRouter()
logger = get_logger("api.routes")


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


async def _log_request(
    db: AsyncSession,
    request_id: str,
    model: str,
    status: str,
    latency_ms: Optional[float],
    error: Optional[str],
) -> None:
    try:
        log = RequestLog(
            request_id=request_id,
            model=model,
            status=status,
            latency_ms=latency_ms,
            error=error,
        )
        db.add(log)
        await db.commit()
    except Exception as exc:
        logger.error("audit log failed request_id=%s: %s", request_id, exc)


@router.post("/predict", response_model=PredictResponse)
async def predict(
    body: PredictRequest,
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    cb = CircuitBreaker(redis, body.model, config.CB_FAILURE_THRESHOLD, config.CB_RECOVERY_TIMEOUT)

    if await cb.is_open():
        CB_OPEN.labels(model=body.model).set(1)
        raise HTTPException(
            status_code=503,
            detail=f"Circuit open for model '{body.model}' — service degraded, try again later",
        )

    request_id = generate_request_id()
    start_time = time.time()

    job = InferenceJob(
        request_id=request_id,
        model=body.model,
        input=body.input,
        created_at=start_time,
    )

    await redis.lpush(INCOMING_QUEUE, job.to_json())
    QUEUE_LENGTH.labels(model=body.model).inc()
    logger.info("queued job=%s model=%s", request_id, body.model)

    result_redis_key = result_key(request_id)
    deadline = time.time() + config.REQUEST_TIMEOUT

    while time.time() < deadline:
        raw = await redis.get(result_redis_key)
        if raw:
            result = InferenceResult.from_json(raw)
            elapsed = time.time() - start_time

            if result.status == JobStatus.FAILED:
                await cb.record_failure()
                CB_OPEN.labels(model=body.model).set(1 if await cb.is_open() else 0)
            else:
                await cb.record_success()
                CB_OPEN.labels(model=body.model).set(0)

            await _log_request(db, request_id, body.model, result.status.value, result.latency_ms, result.error)

            REQUEST_LATENCY.labels(model=body.model).observe(elapsed)
            REQUEST_COUNT.labels(model=body.model, status=result.status.value).inc()
            QUEUE_LENGTH.labels(model=body.model).dec()
            logger.info("completed job=%s elapsed=%.3fs", request_id, elapsed)
            return PredictResponse(
                request_id=request_id,
                model=result.model,
                prediction=result.prediction,
                latency_ms=result.latency_ms,
                status=result.status,
            )
        await asyncio.sleep(config.POLL_INTERVAL)

    await _log_request(db, request_id, body.model, "timeout", None, "request timed out")
    TIMEOUT_COUNT.labels(model=body.model).inc()
    REQUEST_COUNT.labels(model=body.model, status="timeout").inc()
    QUEUE_LENGTH.labels(model=body.model).dec()
    logger.warning("timeout job=%s", request_id)
    raise HTTPException(status_code=504, detail=f"Request {request_id} timed out")


@router.get("/status/{request_id}", response_model=StatusResponse)
async def get_status(
    request_id: str,
    redis: aioredis.Redis = Depends(get_redis),
):
    raw = await redis.get(result_key(request_id))
    if not raw:
        return StatusResponse(request_id=request_id, status=JobStatus.QUEUED)
    result = InferenceResult.from_json(raw)
    return StatusResponse(
        request_id=request_id,
        status=result.status,
        prediction=result.prediction,
        latency_ms=result.latency_ms,
        error=result.error,
    )


@router.get("/health", response_model=HealthResponse)
async def health(redis: aioredis.Redis = Depends(get_redis)):
    try:
        await redis.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"
    return HealthResponse(status="ok", redis=redis_status)
