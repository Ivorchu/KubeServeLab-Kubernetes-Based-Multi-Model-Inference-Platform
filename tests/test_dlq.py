import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from services.api.app.main import app
from services.api.app.routes import get_redis
from shared.protocol import DLQ_KEY, InferenceJob


def _job(request_id: str = "job-1", retry_count: int = 3) -> InferenceJob:
    return InferenceJob(
        request_id=request_id,
        model="text-small",
        input="hello",
        created_at=time.time(),
        retry_count=retry_count,
    )


def _make_redis(dlq_jobs: list[InferenceJob] | None = None):
    mock = AsyncMock()
    mock.aclose = AsyncMock()
    raws = [j.to_json() for j in (dlq_jobs or [])]
    mock.lrange.return_value = raws
    mock.lrem.return_value = 1
    mock.lpush.return_value = 1
    return mock


def test_list_dlq_empty():
    async def _dep():
        yield _make_redis([])

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    resp = client.get("/admin/dlq")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["jobs"] == []
    app.dependency_overrides.clear()


def test_list_dlq_returns_jobs():
    jobs = [_job("id-1", retry_count=3), _job("id-2", retry_count=3)]

    async def _dep():
        yield _make_redis(jobs)

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    resp = client.get("/admin/dlq")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["jobs"][0]["request_id"] == "id-1"
    assert data["jobs"][1]["request_id"] == "id-2"
    app.dependency_overrides.clear()


def test_replay_job_found():
    job = _job("replay-id", retry_count=3)

    async def _dep():
        yield _make_redis([job])

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    resp = client.post("/admin/dlq/replay-id/replay")
    assert resp.status_code == 200
    data = resp.json()
    assert data["request_id"] == "replay-id"
    assert data["status"] == "requeued"
    app.dependency_overrides.clear()


def test_replay_resets_retry_count():
    job = _job("replay-id", retry_count=3)
    captured = {}

    async def _dep():
        mock = _make_redis([job])

        async def fake_lpush(key, raw):
            captured["raw"] = raw
            return 1

        mock.lpush.side_effect = fake_lpush
        yield mock

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    client.post("/admin/dlq/replay-id/replay")

    replayed = InferenceJob.from_json(captured["raw"])
    assert replayed.retry_count == 0
    assert replayed.request_id == "replay-id"
    app.dependency_overrides.clear()


def test_replay_job_not_found():
    async def _dep():
        yield _make_redis([])

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    resp = client.post("/admin/dlq/nonexistent/replay")
    assert resp.status_code == 404
    app.dependency_overrides.clear()
