import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Type, TypeVar


T = TypeVar("T")


class CircuitBreakerOpenError(Exception):
    pass


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout_s: float = 30.0
    half_open_successes: int = 2


class CircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig):
        self._config = config
        self._state = "closed"
        self._failures = 0
        self._half_open_successes = 0
        self._opened_at: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "failures": self._failures,
            "half_open_successes": self._half_open_successes,
            "opened_at": self._opened_at,
            "recovery_timeout_s": self._config.recovery_timeout_s,
            "failure_threshold": self._config.failure_threshold,
            "half_open_successes_target": self._config.half_open_successes,
        }

    async def _before_call(self) -> None:
        if self._state == "open":
            assert self._opened_at is not None
            if time.time() - self._opened_at >= self._config.recovery_timeout_s:
                self._state = "half_open"
                self._half_open_successes = 0
                return
            raise CircuitBreakerOpenError("Circuit breaker is open")

    async def on_success(self) -> None:
        if self._state == "half_open":
            self._half_open_successes += 1
            if self._half_open_successes >= self._config.half_open_successes:
                self._state = "closed"
                self._failures = 0
                self._half_open_successes = 0
                self._opened_at = None
            return

        self._failures = 0

    async def on_failure(self) -> None:
        if self._state == "half_open":
            self._state = "open"
            self._opened_at = time.time()
            self._failures = self._config.failure_threshold
            self._half_open_successes = 0
            return

        self._failures += 1
        if self._failures >= self._config.failure_threshold:
            self._state = "open"
            self._opened_at = time.time()

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:
            await self._before_call()
        try:
            result = await fn()
        except Exception:
            async with self._lock:
                await self.on_failure()
            raise
        else:
            async with self._lock:
                await self.on_success()
            return result


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    base_delay_s: float,
    max_delay_s: float,
    retry_on: tuple[Type[BaseException], ...],
    timeout_s: Optional[float] = None,
) -> T:
    last_err: Optional[BaseException] = None
    for i in range(attempts):
        try:
            if timeout_s is None:
                return await fn()
            return await asyncio.wait_for(fn(), timeout=timeout_s)
        except retry_on as e:
            last_err = e
            if i == attempts - 1:
                break
            delay = min(max_delay_s, base_delay_s * (2**i))
            delay = delay + random.random() * (delay * 0.1)
            await asyncio.sleep(delay)
    assert last_err is not None
    raise last_err

