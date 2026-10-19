from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkerMetadata:
    worker_id: str
    hostname: str
    endpoint: str
    health: str = "unknown"
    readiness: str = "unknown"
    active_requests: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    last_heartbeat: str | None = None
    accelerator_type: str = "cpu"
    accelerator_count: int = 0
    consecutive_failures: int = 0
    last_error: str | None = None
    state: str = "unknown"
    labels: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def schedulable(self) -> bool:
        return self.health == "healthy" and self.readiness == "ready" and self.state == "healthy"


@dataclass(frozen=True)
class RouteMetadata:
    selected_worker_id: str
    policy: str
    worker_health: str
    active_request_count: int
    route_timestamp: str
    request_id: str
    retry_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
