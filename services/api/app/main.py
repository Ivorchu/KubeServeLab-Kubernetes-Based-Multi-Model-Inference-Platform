from fastapi import FastAPI
from prometheus_client import make_asgi_app

from .routes import router

app = FastAPI(
    title="KubeServeLab API",
    version="0.1.0",
    description="Multi-model inference platform API",
)

app.include_router(router)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
