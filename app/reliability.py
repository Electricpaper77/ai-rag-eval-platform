from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 1
    backoff_seconds: float = 0.02


@dataclass(frozen=True)
class TimeoutPolicy:
    seconds: float = 10.0


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at >= self.reset_seconds:
            self.failures = 0
            self.opened_at = None
            return False
        return True

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()


async def call_with_retry(coro_factory, retry: RetryPolicy, timeout: TimeoutPolicy) -> T:
    last_error: Exception | None = None
    for attempt in range(retry.max_retries + 1):
        try:
            return await asyncio.wait_for(coro_factory(), timeout=timeout.seconds)
        except Exception as exc:  # noqa: BLE001 - gateway retries heterogeneous backend failures.
            last_error = exc
            if attempt < retry.max_retries:
                await asyncio.sleep(retry.backoff_seconds * (attempt + 1))
    assert last_error is not None
    raise last_error

