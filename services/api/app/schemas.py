from typing import Any, Optional

from pydantic import BaseModel

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
