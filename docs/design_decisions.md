# Design Decisions

## Synchronous-looking API over async workers

`POST /predict` polls Redis for a result and returns it inline (up to `REQUEST_TIMEOUT` seconds).
This gives clients a simple request/response interface while still decoupling the API from workers.
`GET /status/{request_id}` exists for clients that prefer a truly async pattern.

**Trade-off:** Long-polling in the API ties up a FastAPI worker coroutine per request.
At high concurrency this can be addressed by reducing `REQUEST_TIMEOUT` or switching to WebSocket/SSE push in a later phase.

## Per-model Redis queues

Each model gets its own list key (`queue:text-small`, `queue:text-large`, etc.).
Workers use `BRPOP` across all their supported queues.

**Alternative considered:** A single `queue:incoming` with a scheduler routing to model queues.
This is the Phase 3 design — it enables routing logic (input length, model priority) without changing the API.

## Fake model implementations

`services/worker/app/models.py` uses sleep-based stubs instead of real models.
This keeps Phase 1-2 runnable without GPU or large downloads.
The `MODEL_REGISTRY` dict is the only thing that needs to change when adding real models.

## No message broker (Kafka, RabbitMQ)

Redis is sufficient for the MVP and avoids operational complexity.
If ordering guarantees, fan-out, or replay become necessary, migrating to Kafka is straightforward because `InferenceJob` and `InferenceResult` already use JSON serialization.

## PYTHONPATH-based imports

All services share `shared/` via `PYTHONPATH=/app` in Docker and `PYTHONPATH=.` locally.
This avoids publishing `shared` as a package or using git submodules.
