import os

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
SUPPORTED_MODELS: list[str] = os.getenv(
    "SUPPORTED_MODELS", "text-small,text-large,image-small"
).split(",")
POLL_TIMEOUT: int = int(os.getenv("POLL_TIMEOUT", "1"))
RESULT_TTL: int = int(os.getenv("RESULT_TTL", "300"))
TEXT_LARGE_THRESHOLD: int = int(os.getenv("TEXT_LARGE_THRESHOLD", "200"))
HEALTH_PORT: int = int(os.getenv("SCHEDULER_HEALTH_PORT", "8080"))
