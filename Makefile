.PHONY: up down build logs scale-workers test lint format health predict clean load-test

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

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
