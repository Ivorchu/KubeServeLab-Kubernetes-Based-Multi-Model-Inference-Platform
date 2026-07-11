# KubeServeLab

A production-grade Kubernetes inference platform for serving ML models reliably under load.

Built to demonstrate distributed systems patterns used in real ML serving infrastructure: async job queuing, per-model routing, circuit breakers, dead-letter queues, queue-driven autoscaling (KEDA), and full Prometheus/Grafana observability.

> Models are fake by default (sleep-based stubs) so the platform runs anywhere without a GPU.
> A real [DistilBERT sentiment classifier](#real-model) is included for `text-sentiment`.

---

## Architecture

```
Client
  │
  ▼
FastAPI API (:8000)          ← Circuit breaker, long-poll, audit trail (PostgreSQL)
  │  POST /predict
  │  LPUSH queue:incoming
  ▼
Redis
  ├─ queue:incoming           ← Scheduler BRPOP
  ├─ queue:text-small         ← Worker BRPOP
  ├─ queue:text-large
  ├─ queue:image-small
  ├─ queue:text-sentiment      ← Real DistilBERT model
  ├─ queue:retry              ← Sorted set, score = backoff deadline
  ├─ queue:dlq                ← Dead-letter: exhausted retries
  └─ result:{id}              ← InferenceResult JSON, 300 s TTL
  │
  ▼
Scheduler (:8080)            ← Routes queue:incoming → queue:{model}
  │                             Auto-routes by input length / type
  │                             Requeues retry-ready jobs on backoff deadlines
  ▼
Workers (:9090 metrics)      ← KEDA-scaled 0 → 10 replicas on queue depth
  │  Run inference
  │  On failure: retry queue → DLQ after MAX_RETRIES
  ▼
PostgreSQL (:5432)           ← request_logs: full audit trail
```

### Services

| Service | Port | Role |
|---------|------|------|
| `api` | 8000 | FastAPI gateway: job queuing, long-poll, circuit breaker |
| `worker` | 9090 (metrics) | Inference runner: BRPOP consumer, retry/DLQ |
| `scheduler` | 8080 (health) | Model router: `queue:incoming` → `queue:{model}`, retry requeue |
| `redis` | 6379 | Job queues, result cache, circuit breaker state |
| `postgres` | 5432 | Audit trail (`request_logs` table) |
| `prometheus` | 9091 | Metrics scraping (API + Worker) |
| `grafana` | 3000 | Dashboards |

---

## Key Patterns Implemented

| Pattern | Where | Config |
|---------|-------|--------|
| **Async job queue** | API → Redis → Worker | `REDIS_URL`, `RESULT_TTL` |
| **Per-model routing** | Scheduler (`queue:incoming` → `queue:{model}`) | `SUPPORTED_MODELS` |
| **Exponential backoff retry** | Worker → `queue:retry` → Scheduler | `MAX_RETRIES`, `RETRY_BASE_DELAY_MS` |
| **Dead-letter queue** | Worker → `queue:dlq`, Admin API replay | `MAX_RETRIES` |
| **Circuit breaker** | API (CLOSED → OPEN → HALF_OPEN) | `CB_FAILURE_THRESHOLD`, `CB_RECOVERY_TIMEOUT` |
| **Long-poll response** | API polls `result:{id}` until done or timeout | `REQUEST_TIMEOUT`, `POLL_INTERVAL` |
| **Audit trail** | Every request logged to PostgreSQL | `DATABASE_URL` |
| **KEDA autoscaling** | Workers scale on Redis queue depth | `items-per-replica: 5` |
| **Prometheus metrics** | API + Worker expose `/metrics` | Grafana dashboard included |

---

## Quick Start

```bash
# 1. Configure
cp .env.example .env

# 2. Start all services (API, Worker, Scheduler, Redis, PostgreSQL)
make up

# 3. Verify
make health    # → {"status": "ok", "redis": "ok"}
make predict   # → single prediction round-trip

# 4. Open logs
make logs
```

### With Monitoring

```bash
docker compose --profile monitoring up -d
# Prometheus: http://localhost:9091
# Grafana:    http://localhost:3000  (admin / admin)
```

The Grafana dashboard auto-provisions from `infra/grafana/dashboard.json`.

---

## API

### Predict

```bash
curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"model": "text-small", "input": "this movie is great"}'
```
```json
{
  "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "model": "text-small",
  "prediction": {"label": "positive", "confidence": 0.91},
  "latency_ms": 31.4,
  "status": "done"
}
```

### Real DistilBERT sentiment (text-sentiment)

```bash
curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"model": "text-sentiment", "input": "This platform is incredibly well-built"}'
```
```json
{
  "model": "text-sentiment",
  "prediction": {"label": "POSITIVE", "score": 0.9998},
  "latency_ms": 187.2,
  "status": "done"
}
```

### Async status poll

```bash
curl http://localhost:8000/status/{request_id}
```

### Admin endpoints

```bash
# List dead-letter queue
curl http://localhost:8000/admin/dlq

# Replay a failed job
curl -X POST http://localhost:8000/admin/dlq/{request_id}/replay

# Circuit breaker states
curl http://localhost:8000/admin/circuit-breakers

# Audit log
curl "http://localhost:8000/admin/requests?model=text-small&status=done"
```

### Response codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 503 | Circuit breaker open — model unavailable |
| 504 | Timeout — no worker result within `REQUEST_TIMEOUT` |

---

## Real Model

`text-sentiment` uses [distilbert-base-uncased-finetuned-sst-2-english](https://huggingface.co/distilbert-base-uncased-finetuned-sst-2-english) from HuggingFace — a 268 MB DistilBERT model fine-tuned for binary sentiment classification.

The model is lazy-loaded on first request (no startup delay) and runs on CPU. It is registered alongside the fake stubs in `services/worker/app/models.py` and routed via its own queue (`queue:text-sentiment`) so it doesn't share workers with stub models.

To add your own model, implement a callable with signature `(input: Any) -> dict` and register it in `MODEL_REGISTRY`.

---

## Resilience in Detail

### Circuit Breaker

```
CLOSED ──(5 failures)──► OPEN ──(60 s)──► HALF_OPEN
  ▲                                             │
  └──────── success ──────────────────────────►─┘
```

State persisted in Redis (`cb:{model}:state`). API returns `503` when open. All states visible via `GET /admin/circuit-breakers`.

### Retry + Dead-Letter Queue

```
Worker failure
  → retry_count < MAX_RETRIES (3)?
      YES → queue:retry (sorted set, score = now + backoff_ms)
              Scheduler picks up when deadline passes → queue:incoming
      NO  → queue:dlq
              Admin API: POST /admin/dlq/{id}/replay → reset & requeue
```

Backoff: `500 ms × 2^retry_count` → 500 ms, 1 s, 2 s.

---

## KEDA Autoscaling

Workers scale on Redis queue depth (not CPU), using a KEDA `ScaledObject` (`infra/k8s/hpa-worker.yaml`):

- **Min replicas:** 0 — scales to zero when idle
- **Max replicas:** 10
- **Trigger:** 5 jobs per worker across all model queues
- **Polling interval:** 5 s, **cooldown:** 30 s

```bash
# Deploy to Kubernetes
make k8s-build && make k8s-load && make k8s-deploy
make k8s-keda-install      # install KEDA + apply ScaledObject
make k8s-monitoring-up     # deploy Prometheus + Grafana
make k8s-status            # kubectl get pods -n kubeservelab
```

---

## Observability

### Prometheus Metrics

**API** (`:8000/metrics`):
- `api_requests_total{model, status}` — throughput counter
- `api_request_latency_seconds{model}` — end-to-end latency histogram
- `api_queue_length{model}` — live queue depth gauge
- `api_timeouts_total{model}` — 504 counter
- `api_circuit_breaker_open{model}` — 0/1 gauge

**Worker** (`:9090/metrics`):
- `worker_jobs_total{model, status}` — processed counter
- `worker_inference_latency_seconds{model}` — inference-only latency histogram

### Grafana Dashboard (8 panels)

| Panel | Signal |
|-------|--------|
| Request rate by status | Throughput health |
| Error rate % | SLO indicator |
| API latency p50/p95/p99 | Tail latency |
| Worker inference latency | Model performance |
| Queue depth | Backpressure |
| Worker throughput | Jobs/s |
| Circuit breaker state | Availability |
| Timeout rate | Overload indicator |

---

## Load Testing

```bash
# Interactive Locust UI (http://localhost:8089)
make load-test

# Automated 3-experiment suite (baseline / burst / overload)
make experiment
# Output: experiments/<timestamp>/summary.md + results.json
```

Three Locust user profiles:

| Profile | Users | Wait | Pattern |
|---------|-------|------|---------|
| `BaselineUser` | 10 | 0.1–0.5 s | Mixed models |
| `BurstUser` | 50 | 0.01–0.05 s | text-small heavy |
| `OverloadUser` | 100 | 0 s | Full saturation |

See [`docs/results.md`](docs/results.md) for experiment results.

---

## Testing

```bash
# All tests
make test

# Individual suites
pytest tests/test_api.py -v
pytest tests/test_circuit_breaker.py -v
pytest tests/test_retry.py -v
pytest tests/test_dlq.py -v
pytest tests/test_routing.py -v
pytest tests/test_audit.py -v
```

Tests use `pytest-asyncio` + `httpx` with mocked Redis and PostgreSQL — no real infrastructure required.

---

## Configuration

Copy `.env.example` to `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379` | Redis connection |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection |
| `RESULT_TTL` | `300` | Result cache TTL (s) |
| `REQUEST_TIMEOUT` | `30` | API poll timeout (s) |
| `POLL_INTERVAL` | `0.1` | Redis poll interval (s) |
| `SUPPORTED_MODELS` | `text-small,text-large,image-small,text-sentiment` | Active models |
| `MAX_RETRIES` | `3` | Worker retry attempts |
| `RETRY_BASE_DELAY_MS` | `500` | Exponential backoff base (ms) |
| `CB_FAILURE_THRESHOLD` | `5` | Failures before circuit opens |
| `CB_RECOVERY_TIMEOUT` | `60` | Circuit recovery window (s) |
| `TEXT_LARGE_THRESHOLD` | `200` | Chars to auto-route to text-large |

---

## Project Structure

```
services/
  api/          FastAPI gateway (async)
  worker/       Inference worker (sync, BRPOP)
  scheduler/    Model router + retry requeue (sync, BRPOP)
shared/
  protocol.py   InferenceJob + InferenceResult dataclasses, Redis key constants
  logging.py    Centralized structured logging
infra/
  k8s/          Kubernetes manifests (namespace, deployments, KEDA, monitoring)
  prometheus/   prometheus.yaml + alerts.yaml
  grafana/      dashboard.json + provisioning/
load_tests/
  locustfile.py 3 user profiles
scripts/
  run_experiments.py  Automated load test runner + Prometheus collector
alembic/        Async SQLAlchemy migrations
tests/          pytest unit + integration tests (8 suites)
docs/           Architecture, design decisions, experiment results
```

---

## Phase Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ | FastAPI MVP with fake inference |
| 2 | ✅ | Redis queue + Worker + long-poll API |
| 3 | ✅ | Scheduler with per-model routing + auto-routing |
| 4 | ✅ | Retry / DLQ / circuit breaker / PostgreSQL audit trail |
| 5 | ✅ | Kubernetes manifests (namespace, deployments, Ingress) |
| 6 | ✅ | Prometheus + Grafana observability stack |
| 7 | ✅ | Locust load tests + KEDA queue-depth autoscaling |

---

## Design Decisions

**Synchronous-looking API over async workers.** `POST /predict` polls Redis inline and returns the result — clients get a simple request/response interface while the API and workers are fully decoupled. Trade-off: one coroutine is held per in-flight request. Mitigated by a short `REQUEST_TIMEOUT`; a WebSocket/SSE push model would eliminate this.

**Per-model Redis queues.** Each model gets its own list key so workers bind to exactly the queues they serve. The scheduler (Phase 3) provides a single `queue:incoming` intake with routing logic, keeping the API model-agnostic.

**Redis over Kafka/RabbitMQ.** Sufficient for this scale and avoids operational overhead. `InferenceJob` is JSON-serialized throughout so migrating to Kafka is straightforward if fan-out or replay guarantees are needed.

**KEDA over CPU-based HPA.** Workers are I/O-bound and idle between jobs — CPU is a misleading signal. Queue depth is directly proportional to how much work is waiting, making it the correct autoscaling trigger.

**Sync workers, async API.** FastAPI is fully async; workers are synchronous. Blocking inference code (even sleep stubs, let alone real models) is simpler and safer in a sync context.
