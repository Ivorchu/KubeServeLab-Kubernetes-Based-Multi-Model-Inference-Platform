import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from services.api.app.main import app
from services.api.app.routes import get_redis
from shared.protocol import InferenceResult, JobStatus, result_key


def _make_redis_mock(stored_result: InferenceResult | None = None):
    mock = AsyncMock()
    mock.ping.return_value = True
    mock.lpush.return_value = 1
    if stored_result is not None:
        mock.get.return_value = stored_result.to_json()
    else:
        mock.get.return_value = None
    mock.aclose = AsyncMock()
    return mock


async def _override_redis_ok(stored_result: InferenceResult | None = None):
    yield _make_redis_mock(stored_result)


def test_health_ok():
    async def _dep():
        yield _make_redis_mock()

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["redis"] == "ok"
    app.dependency_overrides.clear()


def test_health_redis_down():
    async def _dep():
        mock = AsyncMock()
        mock.ping.side_effect = Exception("connection refused")
        mock.aclose = AsyncMock()
        yield mock

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["redis"] == "error"
    app.dependency_overrides.clear()


def test_predict_returns_result():
    fake_result = InferenceResult(
        request_id="irrelevant",  # routes.py generates its own
        model="text-small",
        prediction={"label": "positive", "confidence": 0.91},
        latency_ms=15.0,
        status=JobStatus.DONE,
    )

    async def _dep():
        yield _make_redis_mock(stored_result=fake_result)

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    resp = client.post("/predict", json={"model": "text-small", "input": "great film"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["model"] == "text-small"
    assert data["prediction"] is not None
    app.dependency_overrides.clear()


def test_predict_timeout():
    async def _dep():
        mock = AsyncMock()
        mock.lpush.return_value = 1
        mock.get.return_value = None  # worker never responds
        mock.aclose = AsyncMock()
        yield mock

    # Patch timeout to 0.2s so the test doesn't hang for 30s
    with patch("services.api.app.routes.config.REQUEST_TIMEOUT", 0.2):
        app.dependency_overrides[get_redis] = _dep
        client = TestClient(app)
        resp = client.post("/predict", json={"model": "text-small", "input": "test"})
        assert resp.status_code == 504
    app.dependency_overrides.clear()


def test_status_not_found():
    async def _dep():
        mock = AsyncMock()
        mock.get.return_value = None
        mock.aclose = AsyncMock()
        yield mock

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    resp = client.get("/status/nonexistent-id")
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    app.dependency_overrides.clear()


def test_status_found():
    fake_result = InferenceResult(
        request_id="abc123",
        model="text-small",
        prediction={"label": "negative", "confidence": 0.88},
        latency_ms=20.0,
        status=JobStatus.DONE,
    )

    async def _dep():
        mock = AsyncMock()
        mock.get.return_value = fake_result.to_json()
        mock.aclose = AsyncMock()
        yield mock

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    resp = client.get("/status/abc123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["prediction"]["label"] == "negative"
    app.dependency_overrides.clear()
