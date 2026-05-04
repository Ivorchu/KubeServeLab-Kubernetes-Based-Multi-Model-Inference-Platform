# KubeServeLab

A Kubernetes-based multi-model inference platform for ML systems practice.  
The focus is **backend infrastructure** for serving models reliably under load — not model training.

## Architecture

```
Client
  │  POST /predict
  ▼
API Service (FastAPI)
  │  LPUSH queue:{model}
  ▼
Redis
  │  BRPOP
  ▼
Worker Service  →  Model Runtime (fake → real)
  │  SETEX result:{request_id}
  ▼
API Service  →  Client
```

Extra services: Prometheus · Grafana · PostgreSQL (planned) · Kubernetes HPA

## Quick start

```bash
# 1. Copy env
cp .env.example .env

# 2. Start API + worker + Redis
make up          # or: docker compose up --build -d

# 3. Check logs
make logs

# 4. Test it
make health
make predict
```

## Example requests

**Predict (text):**
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

**Check status:**
```bash
curl http://localhost:8000/status/{request_id}
```

**Health:**
```bash
curl http://localhost:8000/health
```

**Metrics (Prometheus format):**
```bash
curl http://localhost:8000/metrics
```

## Scaling workers

```bash
# Scale to 3 worker instances
docker compose up -d --scale worker=3
```

## Monitoring stack

```bash
docker compose --profile monitoring up -d
# Prometheus: http://localhost:9091
# Grafana:    http://localhost:3000  (admin / admin)
# Import infra/grafana/dashboard.json to get the KubeServeLab dashboard
```

## Running tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Local dev (no Docker)

Requires Redis running on `localhost:6379`.

```bash
# Terminal 1 — API
PYTHONPATH=. uvicorn services.api.app.main:app --reload

# Terminal 2 — Worker
PYTHONPATH=. python -m services.worker.app.main
```

## Kubernetes (Phase 5)

```bash
# Apply all manifests (requires a running cluster — kind/minikube/Docker Desktop)
kubectl apply -f infra/k8s/namespace.yaml
kubectl apply -f infra/k8s/configmap.yaml
kubectl apply -f infra/k8s/redis.yaml
kubectl apply -f infra/k8s/api-deployment.yaml
kubectl apply -f infra/k8s/worker-deployment.yaml
kubectl apply -f infra/k8s/hpa-worker.yaml
kubectl apply -f infra/k8s/ingress.yaml
```

## Load testing

```bash
# Interactive Locust UI
make load-test

# Headless (20 users, 60s)
make load-test-headless
```

## Phase roadmap

| Phase | Status | Goal |
|-------|--------|------|
| 1 | ✅ | Single-service FastAPI MVP |
| 2 | ✅ | Distributed API + Redis + Worker |
| 3 | 🔲 | Scheduler with model routing |
| 4 | 🔲 | Retry, timeout, dead-letter queue |
| 5 | 🔲 | Kubernetes deployment |
| 6 | 🔲 | Prometheus + Grafana |
| 7 | 🔲 | Load tests + experiment results |

## Project structure

```
services/api/      FastAPI gateway
services/worker/   Inference worker (Redis BRPOP loop)
services/scheduler/  Phase 3 — model routing (placeholder)
shared/            Protocol types shared across services
infra/k8s/         Kubernetes manifests
infra/prometheus/  Prometheus config
infra/grafana/     Grafana dashboard
load_tests/        Locust load test scripts
tests/             Unit + integration tests
docs/              Architecture, design decisions, experiment results
models/            Model loading instructions (replace fake stubs)
```
