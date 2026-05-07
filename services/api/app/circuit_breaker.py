import time
from enum import Enum

import redis.asyncio as aioredis

from shared.logging import get_logger

logger = get_logger("api.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        r: aioredis.Redis,
        model: str,
        failure_threshold: int,
        recovery_timeout: int,
    ):
        self._r = r
        self._model = model
        self._threshold = failure_threshold
        self._timeout = recovery_timeout

    def _key(self, suffix: str) -> str:
        return f"cb:{self._model}:{suffix}"

    async def is_open(self) -> bool:
        state = (await self._r.get(self._key("state"))) or "closed"

        if str(state) == CircuitState.OPEN:
            opened_at = await self._r.get(self._key("opened_at"))
            if opened_at and time.time() - float(opened_at) >= self._timeout:
                await self._r.set(self._key("state"), CircuitState.HALF_OPEN)
                logger.info("circuit half-open model=%s", self._model)
                return False
            return True

        return False

    async def record_success(self) -> None:
        state = (await self._r.get(self._key("state"))) or "closed"
        if str(state) in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            logger.info("circuit closed model=%s", self._model)
        await self._r.set(self._key("state"), CircuitState.CLOSED)
        await self._r.set(self._key("failures"), 0)
        await self._r.delete(self._key("opened_at"))

    async def record_failure(self) -> None:
        state = (await self._r.get(self._key("state"))) or "closed"

        if str(state) == CircuitState.HALF_OPEN:
            await self._r.set(self._key("state"), CircuitState.OPEN)
            await self._r.set(self._key("opened_at"), time.time())
            logger.warning("circuit re-opened (probe failed) model=%s", self._model)
            return

        try:
            failures = int(await self._r.incr(self._key("failures")))
        except (TypeError, ValueError):
            return

        if failures >= self._threshold:
            await self._r.set(self._key("state"), CircuitState.OPEN)
            await self._r.set(self._key("opened_at"), time.time())
            logger.warning("circuit opened model=%s failures=%d", self._model, failures)

    async def get_status(self) -> dict:
        state = (await self._r.get(self._key("state"))) or "closed"
        opened_at = await self._r.get(self._key("opened_at"))
        try:
            failures = int((await self._r.get(self._key("failures"))) or 0)
        except (TypeError, ValueError):
            failures = 0

        if str(state) == CircuitState.OPEN and opened_at:
            if time.time() - float(opened_at) >= self._timeout:
                state = CircuitState.HALF_OPEN

        return {
            "model": self._model,
            "state": str(state),
            "failures": failures,
            "opened_at": float(opened_at) if opened_at else None,
        }
