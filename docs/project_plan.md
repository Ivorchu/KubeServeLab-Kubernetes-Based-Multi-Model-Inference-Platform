# KubeServeLab — Project Plan & Milestones

## Project Goal

Build a production-grade Kubernetes-based multi-model ML inference platform demonstrating distributed systems patterns: async decoupling, per-model routing, resilience (retry, DLQ, circuit breaker), autoscaling, and full observability.

**Scope:** Infrastructure and serving patterns only. Models are fake stubs — swapping in real models is intentional future work.

---

## Phase 1 — FastAPI MVP (Complete: 2026-05-04)

**Goal:** Single-service HTTP endpoint serving fake model inference.

**Deliverables:**
- FastAPI app with `POST /predict` endpoint
- In-process fake model runner (sleep-based latency simulation)
- `GET /health` and `GET /metrics` endpoints
- Dockerfile + docker-compose.yml skeleton
- pytest unit tests for API routes

**Key decisions made:**
- Python 3.11 + FastAPI as the service layer
- Fake models with configurable sleep latency
- Prometheus metrics from the start

---

## Phase 2 — Distributed API + Redis Queue + Worker (Complete: 2026-05-04)

**Goal:** Decouple HTTP gateway from inference via Redis queue and long-polling.

**Deliverables:**
- API pushes `InferenceJob` JSON to `queue:incoming` (Redis List)
- Worker service: BRPOP consumer from `queue:incoming`
- Worker writes `InferenceResult` JSON to `result:{request_id}` (300s TTL)
- API long-polls `result:{request_id}` at 0.1s interval, returns 504 on timeout
- `GET /status/{request_id}` for true async polling
- `shared/protocol.py` with shared dataclasses and Redis key constants
- docker-compose scales workers with `--scale worker=N`

**Key decisions made:**
- Single `queue:incoming` at this stage (no per-model queues yet)
- Long-polling over WebSocket for simplicity
- Sync worker (easier for blocking inference code)

---

## Phase 3 — Scheduler with Model Routing (Complete: 2026-05-06)

**Goal:** Add a scheduler service that routes jobs from `queue:incoming` to per-model queues.

**Deliverables:**
- Scheduler service: BRPOP from `queue:incoming`, LPUSH to `queue:{model}`
- Per-model queues: `queue:text-small`, `queue:text-large`, `queue:image-small`
- Auto-routing logic:
  - Input dict with `image`/`image_url` key → `image-small`
  - Text len ≥ `TEXT_LARGE_THRESHOLD` (200 chars) → `text-large`
  - Otherwise → `text-small`
- Workers bind to a specific model queue via `WORKER_MODEL` env var
- Scheduler health endpoint on :8080
- Tests: `test_routing.py`, `test_scheduler.py`

---

## Phase 4 — Resilience Patterns (Complete: 2026-05-06–07)

**Goal:** Add retry, DLQ, circuit breaker, and audit trail so the system handles failures gracefully.

**Sub-phases (3 commits):**

### 4a — Retry with Exponential Backoff (2026-05-06)
- Failed jobs → `queue:retry` sorted set (score = backoff deadline epoch)
- Backoff: `base_ms * 2^retry_count` (500ms, 1s, 2s)
- Scheduler requeues ready retry items to `queue:incoming`
- Tests: `test_retry.py`

### 4b — Dead-Letter Queue (2026-05-06)
- After `MAX_RETRIES` (3) failures → `queue:dlq`
- Admin API: `GET /admin/dlq`, `POST /admin/dlq/{id}/replay`
- Tests: `test_dlq.py`

### 4c — Circuit Breaker + PostgreSQL Audit Trail (2026-05-07)
- Circuit breaker: CLOSED → OPEN → HALF_OPEN → CLOSED
- Triggers: 5 failures → open; 60s recovery; probe on half-open
- State stored in Redis: `cb:{model}:state`, `cb:{model}:failures`, `cb:{model}:opened_at`
- API returns 503 when circuit OPEN
- Admin API: `GET /admin/circuit-breakers`
- PostgreSQL `request_logs` table via async SQLAlchemy + Alembic
- Audit for every request: model, status, latency_ms, error
- Admin API: `GET /admin/requests?model=&status=`
- Tests: `test_circuit_breaker.py`, `test_audit.py`

---

## Phase 5 — Kubernetes Deployment (Complete: 2026-05-07)

**Goal:** Deploy all services to Kubernetes with proper manifests.

**Deliverables:**
- Namespace `kubeservelab`
- ConfigMap for shared environment variables
- Deployments: API (2 replicas), Worker (2 replicas), Scheduler (1 replica), Redis (1 replica)
- StatefulSet: PostgreSQL (1 replica, PVC 5Gi, headless Service)
- Services: ClusterIP for API/Redis, headless for Worker (Prometheus scraping) and PostgreSQL
- Ingress: `kubeservelab.local` → API
- CPU-based HPA for workers (later replaced in Phase 7)
- Readiness/liveness probes for all services
- Makefile targets: `k8s-build`, `k8s-load`, `k8s-deploy`, `k8s-status`

---

## Phase 6 — Prometheus + Grafana Observability (Complete: 2026-05-10)

**Goal:** Full-stack observability with metrics, dashboards, and alerts.

**Deliverables:**
- Prometheus deployment with RBAC ServiceAccount for pod discovery (PVC 5Gi)
- Prometheus config: scrapes API (:8000/metrics) and Worker pods (:9090/metrics)
- Alert rules: HighErrorRate, HighP99Latency, CircuitBreakerOpen, WorkerInactive
- Grafana deployment (PVC 1Gi, NodePort 30300)
- Grafana auto-provisioned dashboard (8 panels):
  1. Request rate by status
  2. Error rate %
  3. API latency p50/p95/p99
  4. Worker inference latency
  5. Queue depth gauge
  6. Worker throughput
  7. Circuit breaker state (colored stat)
  8. Timeout rate
- Makefile targets: `k8s-monitoring-up`, `port-forward-grafana`
- `--profile monitoring` flag for docker-compose local use

---

## Phase 7 — Load Tests + KEDA Autoscaling (Complete: 2026-05-11–12)

**Goal:** Validate the system under load and switch to queue-driven autoscaling.

**Sub-phases (2 commits):**

### 7a — Locust Load Tests + Experiment Runner (2026-05-11)
- `load_tests/locustfile.py` with 3 user profiles:
  - `BaselineUser`: 10 users, 0.1–0.5s wait, mixed traffic
  - `BurstUser`: 50 users, 0.01–0.05s wait, text-small heavy
  - `OverloadUser`: 100 users, 0s wait, full saturation
- `load_tests/sample_requests.json`: test payload library
- `scripts/run_experiments.py`: automated runner
  - Runs all 3 experiments sequentially
  - Collects Locust CSV stats + Prometheus metrics post-run
  - Generates `experiments/<timestamp>/summary.md` + `results.json`
- Makefile targets: `load-test` (Locust UI), `experiment` (automated runner)

### 7b — KEDA Queue-Length ScaledObject (2026-05-12)
- Replaced CPU-based HPA with KEDA ScaledObject in `infra/k8s/hpa-worker.yaml`
- Trigger: Redis queue length (5 items per replica across all model queues)
- Min replicas: 0 (scale to zero when idle)
- Max replicas: 10
- Polling interval: 5s, cooldown: 30s
- Requires KEDA 2.14+ installed: `make k8s-keda-install`

---

## All Phases Complete — Current Status (2026-05-12)

The platform is a complete reference implementation. No open issues or planned Phase 8.

### Potential future extensions (not planned):
- **Phase 8:** Real model integration (replace stub MODEL_REGISTRY entries)
- **Phase 9:** WebSocket or SSE API to eliminate long-poll connection holding
- **Phase 10:** Multi-cluster or multi-region routing
- **Phase 11:** Model versioning and A/B routing in scheduler
- **Phase 12:** Distributed tracing (OpenTelemetry + Jaeger/Tempo)

---

## Git History Reference

| Date | Commit | Phase |
|------|--------|-------|
| 2026-05-04 | `Initial commit` (2074989) | 1 |
| 2026-05-04 | `FastAPI + Redis queue + worker + K8s manifests` (0bca58b) | 2 |
| 2026-05-06 | `Add scheduler service for model routing` (5e9a598) | 3 |
| 2026-05-06 | `Add retry with exponential backoff` (a374fbd) | 4a |
| 2026-05-06 | `Refresh repository metadata` (7b571c8) | — |
| 2026-05-06 | `Add dead-letter queue` (9860cfd) | 4b |
| 2026-05-07 | `Add circuit breaker and PostgreSQL audit trail` (965f84f) | 4c |
| 2026-05-07 | `Add Kubernetes deployment manifests` (3ce0c09) | 5 |
| 2026-05-10 | `Add Prometheus + Grafana observability stack` (88ae40f) | 6 |
| 2026-05-11 | `Add Locust load experiments and experiment runner` (2ebea4d) | 7a |
| 2026-05-12 | `Replace CPU HPA with KEDA queue-length ScaledObject` (e1daf1d) | 7b |
