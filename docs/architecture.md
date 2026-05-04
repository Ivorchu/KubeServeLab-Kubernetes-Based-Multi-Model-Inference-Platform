# Architecture

## Request flow

```
Client
  │  POST /predict {"model": "text-small", "input": "..."}
  ▼
API Service (FastAPI :8000)
  │  generates request_id
  │  LPUSH queue:text-small <job_json>
  │  polls RESULT key with timeout
  ▼
Redis
  │  BRPOP queue:text-small
  ▼
Worker Service
  │  runs inference
  │  SETEX result:<request_id> <result_json>
  ▼
API Service  ←  reads result from Redis
  │
  ▼
Client  ←  {"request_id": "...", "prediction": {...}, "latency_ms": 31.4}
```

## Services

| Service | Port | Role |
|---------|------|------|
| `api` | 8000 | Accepts HTTP, pushes jobs to Redis, returns results |
| `worker` | 9090 (metrics) | Polls Redis, runs inference, writes results |
| `redis` | 6379 | Job queues + result store |
| `prometheus` | 9091 | Scrapes metrics (monitoring profile) |
| `grafana` | 3000 | Dashboards (monitoring profile) |

## Redis key schema

| Key pattern | Type | TTL | Purpose |
|-------------|------|-----|---------|
| `queue:{model}` | List | — | Job queue per model (LPUSH/BRPOP) |
| `result:{request_id}` | String | 300s | Worker result, read by API |

## Prometheus metrics

**API service** (scraped at `:8000/metrics`):
- `api_requests_total{model, status}` — request count by outcome
- `api_request_latency_seconds{model}` — histogram of end-to-end latency
- `api_queue_length{model}` — gauge of in-flight requests
- `api_timeouts_total{model}` — requests that exceeded `REQUEST_TIMEOUT`

**Worker service** (scraped at `:9090`):
- `worker_jobs_total{model, status}` — jobs processed
- `worker_inference_latency_seconds{model}` — histogram of model-only latency

## Phase roadmap

| Phase | Focus |
|-------|-------|
| 1 | Single-service FastAPI MVP |
| 2 (current) | Distributed API + Redis + Worker |
| 3 | Scheduler service with explicit model routing |
| 4 | Timeouts, retries, dead-letter queue, health checks |
| 5 | Kubernetes deployment (kind/minikube → cloud) |
| 6 | Prometheus + Grafana observability |
| 7 | Locust load testing, experiments, results |
