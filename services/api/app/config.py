import os


REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
RESULT_TTL: int = int(os.getenv("RESULT_TTL", "300"))
REQUEST_TIMEOUT: float = float(os.getenv("REQUEST_TIMEOUT", "30"))
POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", "0.1"))
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
SUPPORTED_MODELS: list[str] = os.getenv(
    "SUPPORTED_MODELS", "text-small,text-large,image-small"
).split(",")
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://kubeservelab:kubeservelab@localhost:5432/kubeservelab",
)
CB_FAILURE_THRESHOLD: int = int(os.getenv("CB_FAILURE_THRESHOLD", "5"))
CB_RECOVERY_TIMEOUT: int = int(os.getenv("CB_RECOVERY_TIMEOUT", "60"))
