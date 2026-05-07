from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from shared.protocol import JobStatus


class PredictRequest(BaseModel):
    model: str
    input: Any

    model_config = {
        "json_schema_extra": {
            "example": {"model": "text-small", "input": "this movie is great"}
        }
    }


class PredictResponse(BaseModel):
    request_id: str
    model: str
    prediction: Optional[Any] = None
    latency_ms: Optional[float] = None
    status: JobStatus


class StatusResponse(BaseModel):
    request_id: str
    status: JobStatus
    prediction: Optional[Any] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    redis: str


class DLQJobResponse(BaseModel):
    request_id: str
    model: str
    input: Any
    created_at: float
    retry_count: int


class DLQListResponse(BaseModel):
    count: int
    jobs: list[DLQJobResponse]


class ReplayResponse(BaseModel):
    request_id: str
    status: str


class CircuitBreakerStatus(BaseModel):
    model: str
    state: str
    failures: int
    opened_at: Optional[float] = None


class CircuitBreakerListResponse(BaseModel):
    circuit_breakers: list[CircuitBreakerStatus]


class RequestLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    model: str
    status: str
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    created_at: datetime


class RequestLogListResponse(BaseModel):
    count: int
    requests: list[RequestLogResponse]
