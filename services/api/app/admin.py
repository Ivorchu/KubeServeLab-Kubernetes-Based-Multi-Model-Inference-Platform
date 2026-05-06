from fastapi import APIRouter, Depends, HTTPException

import redis.asyncio as aioredis

from shared.protocol import DLQ_KEY, INCOMING_QUEUE, InferenceJob

from .routes import get_redis
from .schemas import DLQJobResponse, DLQListResponse, ReplayResponse

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
