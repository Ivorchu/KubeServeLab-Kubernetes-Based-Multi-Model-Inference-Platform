import os

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
RESULT_TTL: int = int(os.getenv("RESULT_TTL", "300"))
WORKER_ID: str = os.getenv("WORKER_ID", "worker-1")
SUPPORTED_MODELS: list[str] = os.getenv(
    "SUPPORTED_MODELS", "text-small,text-large,image-small"
).split(",")
POLL_TIMEOUT: int = int(os.getenv("POLL_TIMEOUT", "1"))
METRICS_PORT: int = int(os.getenv("WORKER_METRICS_PORT", "9090"))
