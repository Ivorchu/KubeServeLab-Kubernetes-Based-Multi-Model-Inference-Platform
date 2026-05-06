import json
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class InferenceJob:
    request_id: str
    model: str
    input: Any
    created_at: float
    retry_count: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "InferenceJob":
        return cls(**json.loads(data))


@dataclass
class InferenceResult:
    request_id: str
    model: str
    prediction: Any
    latency_ms: float
    status: JobStatus
    error: Optional[str] = None

    def to_json(self) -> str:
        d = asdict(self)
        d["status"] = self.status.value
        return json.dumps(d)

    @classmethod
    def from_json(cls, data: str) -> "InferenceResult":
        d = json.loads(data)
        d["status"] = JobStatus(d["status"])
        return cls(**d)


def generate_request_id() -> str:
    return str(uuid.uuid4())


# Redis key helpers
INCOMING_QUEUE = "queue:incoming"
RETRY_QUEUE = "queue:retry"
DLQ_KEY = "queue:dlq"

def job_queue_key(model: str) -> str:
    return f"queue:{model}"

def result_key(request_id: str) -> str:
    return f"result:{request_id}"
