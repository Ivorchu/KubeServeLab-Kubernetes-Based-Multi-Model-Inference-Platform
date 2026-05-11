.PHONY: up down build logs scale-workers test lint format health predict clean load-test \
        k8s-build k8s-load k8s-deploy k8s-status k8s-logs k8s-smoke k8s-delete \
        k8s-monitoring-up k8s-monitoring-down k8s-grafana k8s-prometheus \
        experiment experiment-baseline experiment-burst experiment-overload

# ── Docker Compose ──────────────────────────────────────────────────────────

up:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

scale-workers:
	docker compose up -d --scale worker=$(n)

monitoring-up:
	docker compose --profile monitoring up -d

# ── Local dev ───────────────────────────────────────────────────────────────

install:
	pip install -r requirements.txt

# Run API locally (requires Redis on localhost:6379)
run-api:
	PYTHONPATH=. uvicorn services.api.app.main:app --host 0.0.0.0 --port 8000 --reload

# Run worker locally (requires Redis on localhost:6379)
run-worker:
	PYTHONPATH=. python -m services.worker.app.main

# ── Tests ───────────────────────────────────────────────────────────────────

test:
	pytest tests/ -v

test-api:
	pytest tests/test_api.py -v

test-worker:
	pytest tests/test_worker.py -v

# ── Lint / Format ────────────────────────────────────────────────────────────

lint:
	ruff check services/ shared/ tests/

format:
	ruff format services/ shared/ tests/

# ── Smoke tests (requires running stack) ─────────────────────────────────────

health:
	curl -s http://localhost:8000/health

predict:
	curl -s -X POST http://localhost:8000/predict \
		-H "Content-Type: application/json" \
		-d "{\"model\": \"text-small\", \"input\": \"this movie is great\"}"

predict-large:
	curl -s -X POST http://localhost:8000/predict \
		-H "Content-Type: application/json" \
		-d "{\"model\": \"text-large\", \"input\": \"a long review about the film\"}"

# ── Load testing ─────────────────────────────────────────────────────────────

load-test:
	locust -f load_tests/locustfile.py --host http://localhost:8000

load-test-headless:
	locust -f load_tests/locustfile.py --host http://localhost:8000 \
		--headless -u 20 -r 5 --run-time 60s

# ── Kubernetes (kind) ─────────────────────────────────────────────────────────
# Requires: kind, kubectl
# One-time cluster setup: kind create cluster --name kubeservelab

k8s-build:
	docker build -t kubeservelab/api:latest -f services/api/Dockerfile .
	docker build -t kubeservelab/worker:latest -f services/worker/Dockerfile .
	docker build -t kubeservelab/scheduler:latest -f services/scheduler/Dockerfile .

k8s-load:
	kind load docker-image kubeservelab/api:latest --name kubeservelab
	kind load docker-image kubeservelab/worker:latest --name kubeservelab
	kind load docker-image kubeservelab/scheduler:latest --name kubeservelab

k8s-deploy:
	kubectl apply -f infra/k8s/namespace.yaml
	kubectl apply -f infra/k8s/

k8s-status:
	kubectl get pods -n kubeservelab
	kubectl get svc -n kubeservelab

k8s-logs:
	kubectl logs -n kubeservelab -l app=api --tail=50 --prefix
	kubectl logs -n kubeservelab -l app=worker --tail=50 --prefix

k8s-smoke:
	kubectl port-forward -n kubeservelab svc/api 8000:80 &
	sleep 2
	curl -s http://localhost:8000/health
	curl -s -X POST http://localhost:8000/predict \
		-H "Content-Type: application/json" \
		-d '{"model": "text-small", "input": "hello world"}'

k8s-delete:
	kubectl delete namespace kubeservelab

k8s-monitoring-up:
	kubectl apply -f infra/k8s/monitoring.yaml

k8s-monitoring-down:
	kubectl delete -f infra/k8s/monitoring.yaml

# Open Grafana at http://localhost:3000  (admin/admin)
k8s-grafana:
	kubectl port-forward -n kubeservelab svc/grafana 3000:3000

# Open Prometheus at http://localhost:9090
k8s-prometheus:
	kubectl port-forward -n kubeservelab svc/prometheus 9090:9090

# ── Load experiments ──────────────────────────────────────────────────────────
# Requires: stack running + Prometheus port-forwarded to :9090
# Run all three scenarios sequentially and write experiments/<ts>/summary.md
experiment:
	python scripts/run_experiments.py

experiment-baseline:
	python scripts/run_experiments.py --experiment baseline

experiment-burst:
	python scripts/run_experiments.py --experiment burst

experiment-overload:
	python scripts/run_experiments.py --experiment overload

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
