import asyncio
import time
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException

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
from .metrics import QUEUE_LENGTH, REQUEST_COUNT, REQUEST_LATENCY, TIMEOUT_COUNT
from .schemas import HealthResponse, PredictRequest, PredictResponse, StatusResponse

router = APIRouter()
logger = get_logger("api.routes")


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@router.post("/predict", response_model=PredictResponse)
async def predict(
    body: PredictRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
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

    # Poll for the worker result until timeout
    result_redis_key = result_key(request_id)
    deadline = time.time() + config.REQUEST_TIMEOUT

    while time.time() < deadline:
        raw = await redis.get(result_redis_key)
        if raw:
            result = InferenceResult.from_json(raw)
            elapsed = time.time() - start_time
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
