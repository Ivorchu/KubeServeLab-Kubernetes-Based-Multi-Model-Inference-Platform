from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from shared.logging import get_logger

from .admin import router as admin_router
from .database import init_db
from .routes import router

logger = get_logger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
    except Exception as exc:
        logger.warning("DB initialization failed (postgres unavailable?): %s", exc)
    yield


app = FastAPI(
    title="KubeServeLab API",
    version="0.1.0",
    description="Multi-model inference platform API",
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(admin_router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
