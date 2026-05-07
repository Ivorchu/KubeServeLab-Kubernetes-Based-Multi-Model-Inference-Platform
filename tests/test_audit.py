from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from services.api.app.main import app
from services.api.app.routes import get_redis


def test_list_requests_returns_empty():
    # DB mock from conftest returns [] by default
    client = TestClient(app)
    resp = client.get("/admin/requests")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["requests"] == []


def test_list_requests_accepts_filters():
    client = TestClient(app)
    resp = client.get("/admin/requests?model=text-small&status=done&limit=10")
    assert resp.status_code == 200


def test_circuit_breakers_returns_all_models():
    async def _dep():
        mock = AsyncMock()
        mock.get.return_value = None  # all circuits closed
        mock.aclose = AsyncMock()
        yield mock

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    resp = client.get("/admin/circuit-breakers")
    assert resp.status_code == 200
    data = resp.json()
    assert "circuit_breakers" in data
    models = [cb["model"] for cb in data["circuit_breakers"]]
    assert "text-small" in models
    assert "text-large" in models
    assert "image-small" in models
    for cb in data["circuit_breakers"]:
        assert cb["state"] == "closed"
    app.dependency_overrides.clear()
