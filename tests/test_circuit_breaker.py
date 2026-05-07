import time
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from services.api.app.circuit_breaker import CircuitBreaker, CircuitState
from services.api.app.main import app
from services.api.app.routes import get_redis


def _redis(state="closed", opened_at=None, failures=0):
    mock = AsyncMock()

    async def fake_get(key):
        if ":state" in key:
            return state
        elif ":opened_at" in key:
            return str(opened_at) if opened_at else None
        elif ":failures" in key:
            return str(failures)
        return None

    mock.get.side_effect = fake_get
    mock.set.return_value = True
    mock.delete.return_value = 1
    mock.incr.return_value = failures + 1
    return mock


async def test_closed_is_not_open():
    cb = CircuitBreaker(_redis("closed"), "text-small", failure_threshold=3, recovery_timeout=60)
    assert not await cb.is_open()


async def test_open_within_timeout_is_open():
    cb = CircuitBreaker(
        _redis("open", opened_at=time.time() - 10),
        "text-small", failure_threshold=3, recovery_timeout=60,
    )
    assert await cb.is_open()


async def test_open_past_timeout_transitions_to_half_open():
    r = _redis("open", opened_at=time.time() - 120)
    cb = CircuitBreaker(r, "text-small", failure_threshold=3, recovery_timeout=60)
    assert not await cb.is_open()
    r.set.assert_called()


async def test_failure_below_threshold_stays_closed():
    r = _redis("closed")
    r.incr.return_value = 2
    cb = CircuitBreaker(r, "text-small", failure_threshold=3, recovery_timeout=60)
    await cb.record_failure()
    set_calls = [str(c) for c in r.set.call_args_list]
    assert not any(CircuitState.OPEN in c for c in set_calls)


async def test_failure_at_threshold_opens_circuit():
    r = _redis("closed")
    r.incr.return_value = 3
    cb = CircuitBreaker(r, "text-small", failure_threshold=3, recovery_timeout=60)
    await cb.record_failure()
    r.set.assert_any_call("cb:text-small:state", CircuitState.OPEN)


async def test_success_closes_circuit():
    r = _redis("open")
    cb = CircuitBreaker(r, "text-small", failure_threshold=3, recovery_timeout=60)
    await cb.record_success()
    r.set.assert_any_call("cb:text-small:state", CircuitState.CLOSED)


async def test_failure_in_half_open_reopens():
    r = _redis("half_open")
    cb = CircuitBreaker(r, "text-small", failure_threshold=3, recovery_timeout=60)
    await cb.record_failure()
    r.set.assert_any_call("cb:text-small:state", CircuitState.OPEN)


async def test_success_in_half_open_closes():
    r = _redis("half_open")
    cb = CircuitBreaker(r, "text-small", failure_threshold=3, recovery_timeout=60)
    await cb.record_success()
    r.set.assert_any_call("cb:text-small:state", CircuitState.CLOSED)


def test_predict_503_when_circuit_open():
    async def _dep():
        mock = AsyncMock()
        mock.aclose = AsyncMock()
        mock.lpush.return_value = 1

        async def fake_get(key):
            if ":state" in key:
                return "open"
            elif ":opened_at" in key:
                return str(time.time() - 10)
            return None

        mock.get.side_effect = fake_get
        yield mock

    app.dependency_overrides[get_redis] = _dep
    client = TestClient(app)
    resp = client.post("/predict", json={"model": "text-small", "input": "test"})
    assert resp.status_code == 503
    assert "Circuit open" in resp.json()["detail"]
    app.dependency_overrides.clear()
