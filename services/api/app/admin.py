from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from shared.protocol import DLQ_KEY, INCOMING_QUEUE, InferenceJob

from . import config
from .circuit_breaker import CircuitBreaker
from .database import get_db
from .db_models import RequestLog
from .routes import get_redis
from .schemas import (
    CircuitBreakerListResponse,
    CircuitBreakerStatus,
    DLQJobResponse,
    DLQListResponse,
    ReplayResponse,
    RequestLogListResponse,
    RequestLogResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dlq", response_model=DLQListResponse)
async def list_dlq(redis: aioredis.Redis = Depends(get_redis)):
    raws = await redis.lrange(DLQ_KEY, 0, -1)
    jobs = [DLQJobResponse(**vars(InferenceJob.from_json(r))) for r in raws]
    return DLQListResponse(count=len(jobs), jobs=jobs)


@router.post("/dlq/{request_id}/replay", response_model=ReplayResponse)
async def replay_dlq_job(
    request_id: str,
    redis: aioredis.Redis = Depends(get_redis),
):
    raws = await redis.lrange(DLQ_KEY, 0, -1)
    match = next((r for r in raws if InferenceJob.from_json(r).request_id == request_id), None)

    if match is None:
        raise HTTPException(status_code=404, detail=f"Job {request_id} not found in DLQ")

    replayed = InferenceJob.from_json(match)
    replayed.retry_count = 0

    await redis.lrem(DLQ_KEY, 1, match)
    await redis.lpush(INCOMING_QUEUE, replayed.to_json())

    return ReplayResponse(request_id=request_id, status="requeued")


@router.get("/circuit-breakers", response_model=CircuitBreakerListResponse)
async def list_circuit_breakers(redis: aioredis.Redis = Depends(get_redis)):
    statuses = []
    for model in config.SUPPORTED_MODELS:
        cb = CircuitBreaker(redis, model, config.CB_FAILURE_THRESHOLD, config.CB_RECOVERY_TIMEOUT)
        statuses.append(CircuitBreakerStatus(**await cb.get_status()))
    return CircuitBreakerListResponse(circuit_breakers=statuses)


@router.get("/requests", response_model=RequestLogListResponse)
async def list_requests(
    model: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(RequestLog).order_by(RequestLog.created_at.desc()).limit(limit)
    if model:
        stmt = stmt.where(RequestLog.model == model)
    if status:
        stmt = stmt.where(RequestLog.status == status)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return RequestLogListResponse(
        count=len(logs),
        requests=[RequestLogResponse.model_validate(log) for log in logs],
    )
