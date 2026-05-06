import os

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
SUPPORTED_MODELS: list[str] = os.getenv(
    "SUPPORTED_MODELS", "text-small,text-large,image-small"
).split(",")
POLL_TIMEOUT: int = int(os.getenv("POLL_TIMEOUT", "1"))
# Input length threshold (chars) for routing "auto" text jobs to text-large
TEXT_LARGE_THRESHOLD: int = int(os.getenv("TEXT_LARGE_THRESHOLD", "200"))
