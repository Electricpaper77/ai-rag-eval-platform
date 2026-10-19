"""Deterministic, CPU-safe capacity admission and recommendation primitives."""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass

from fastapi import APIRouter
from prometheus_client import Counter, Gauge


ACTIVE_REQUESTS = Gauge("agenttrust_active_requests", "Requests currently executing")
QUEUED_REQUESTS = Gauge("agenttrust_queued_requests", "Requests waiting for capacity")
CAPACITY_PER_REPLICA = Gauge("agenttrust_capacity_per_replica", "Maximum concurrent requests per replica")
SATURATION_RATIO = Gauge("agenttrust_saturation_ratio", "Current capacity saturation ratio")
SCALING_RECOMMENDATION = Gauge(
    "agenttrust_scaling_recommendation",
    "Current scaling recommendation encoded as scale_up=1, scale_down=-1, hold=0, exhausted=2",
)
BACKPRESSURE_TOTAL = Counter("agenttrust_backpressure_total", "Requests rejected or timed out by capacity admission")


@dataclass(frozen=True)
class CapacitySnapshot:
    current_replicas: int
    ready_replicas: int
    desired_replicas: int
    active_requests: int
    queued_requests: int
    capacity_per_replica: int
    queue_capacity: int
    saturation_ratio: float
    recommendation: str
    reason_code: str


class CapacityExhausted(RuntimeError):
    """Raised when both active capacity and the bounded queue are full."""

    reason_code = "capacity_exhausted"


class CapacityTimeout(RuntimeError):
    """Raised when a queued request cannot acquire capacity before its deadline."""

    reason_code = "capacity_queue_timeout"


class CapacityController:
    def __init__(self, *, capacity_per_replica: int = 4, queue_capacity: int = 8) -> None:
        self.capacity_per_replica = max(1, int(capacity_per_replica))
        self.queue_capacity = max(0, int(queue_capacity))
        self._active = 0
        self._queued = 0
        self._sync_metrics("hold")

    @property
    def current_replicas(self) -> int:
        return max(1, int(os.getenv("GATE9_CURRENT_REPLICAS", "1")))

    @property
    def ready_replicas(self) -> int:
        return max(0, int(os.getenv("GATE9_READY_REPLICAS", str(self.current_replicas))))

    @property
    def desired_replicas(self) -> int:
        return max(1, int(os.getenv("GATE9_DESIRED_REPLICAS", str(self.current_replicas))))

    def _recommendation(self) -> tuple[str, str]:
        capacity = self.current_replicas * self.capacity_per_replica
        saturation = (self._active + self._queued) / max(capacity + self.queue_capacity, 1)
        if self._queued >= self.queue_capacity and self._active >= capacity:
            return "capacity_exhausted", "QUEUE_FULL_AND_ACTIVE_CAPACITY_FULL"
        if self._queued > 0 or self._active >= capacity:
            return "scale_up", "ACTIVE_CAPACITY_OR_QUEUE_PRESSURE"
        if self._active == 0 and self._queued == 0 and saturation < 0.30:
            return "scale_down", "LOW_UTILIZATION_STABLE"
        return "hold", "WITHIN_TARGET"

    def _sync_metrics(self, recommendation: str | None = None) -> None:
        capacity = self.current_replicas * self.capacity_per_replica
        saturation = (self._active + self._queued) / max(capacity + self.queue_capacity, 1)
        ACTIVE_REQUESTS.set(self._active)
        QUEUED_REQUESTS.set(self._queued)
        CAPACITY_PER_REPLICA.set(self.capacity_per_replica)
        SATURATION_RATIO.set(min(1.0, saturation))
        action = recommendation or self._recommendation()[0]
        SCALING_RECOMMENDATION.set({"scale_down": -1, "hold": 0, "scale_up": 1, "capacity_exhausted": 2}[action])

    def snapshot(self) -> CapacitySnapshot:
        recommendation, reason_code = self._recommendation()
        capacity = self.current_replicas * self.capacity_per_replica
        saturation = min(1.0, (self._active + self._queued) / max(capacity + self.queue_capacity, 1))
        return CapacitySnapshot(
            current_replicas=self.current_replicas,
            ready_replicas=self.ready_replicas,
            desired_replicas=self.desired_replicas,
            active_requests=self._active,
            queued_requests=self._queued,
            capacity_per_replica=self.capacity_per_replica,
            queue_capacity=self.queue_capacity,
            saturation_ratio=round(saturation, 4),
            recommendation=recommendation,
            reason_code=reason_code,
        )

    def recommendation(self) -> dict[str, object]:
        snapshot = self.snapshot()
        return {"recommendation": snapshot.recommendation, "reason_code": snapshot.reason_code, **asdict(snapshot)}

    async def acquire(self, timeout_seconds: float = 2.0) -> None:
        capacity = self.current_replicas * self.capacity_per_replica
        deadline = asyncio.get_running_loop().time() + max(0.0, timeout_seconds)
        queued = False
        while True:
            if self._active < capacity:
                if queued:
                    self._queued = max(0, self._queued - 1)
                self._active += 1
                self._sync_metrics()
                return
            if not queued:
                if self._queued >= self.queue_capacity:
                    BACKPRESSURE_TOTAL.inc()
                    self._sync_metrics("capacity_exhausted")
                    raise CapacityExhausted()
                self._queued += 1
                queued = True
                self._sync_metrics()
            if asyncio.get_running_loop().time() >= deadline:
                self._queued = max(0, self._queued - 1)
                BACKPRESSURE_TOTAL.inc()
                self._sync_metrics()
                raise CapacityTimeout()
            await asyncio.sleep(0.02)

    async def release(self) -> None:
        self._active = max(0, self._active - 1)
        self._sync_metrics()


DEFAULT_CONTROLLER = CapacityController(
    capacity_per_replica=int(os.getenv("GATE9_MAX_INFLIGHT_PER_REPLICA", "4")),
    queue_capacity=int(os.getenv("GATE9_QUEUE_CAPACITY", "8")),
)

router = APIRouter(prefix="/platform/capacity", tags=["capacity"])


@router.get("/status")
def capacity_status() -> dict[str, object]:
    return asdict(DEFAULT_CONTROLLER.snapshot())


@router.get("/recommendation")
def capacity_recommendation() -> dict[str, object]:
    return DEFAULT_CONTROLLER.recommendation()
