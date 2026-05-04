import os


REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
RESULT_TTL: int = int(os.getenv("RESULT_TTL", "300"))
REQUEST_TIMEOUT: float = float(os.getenv("REQUEST_TIMEOUT", "30"))
POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", "0.1"))
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
