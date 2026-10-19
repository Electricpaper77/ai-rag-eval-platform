from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CanaryPhase(str, Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    CANARY = "CANARY"
    PROMOTING = "PROMOTING"
    PROMOTED = "PROMOTED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


@dataclass
class CanaryPolicy:
    error_rate_delta: float = 0.01
    latency_ratio: float = 1.25
    minimum_samples: int = 3
    stages: tuple[int, ...] = (5, 25, 100)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelRecord:
    name: str
    version: str
    runtime: str
    endpoint: str
    readiness: str = "unknown"
    rollout_state: str = "standby"
    traffic_weight: int = 0
    latency_p95_ms: float = 0.0
    error_rate: float = 0.0
    request_count: int = 0
    error_count: int = 0
    latency_samples_ms: list[float] = field(default_factory=list, repr=False)

    @property
    def ready(self) -> bool:
        return self.readiness == "ready"

    def record(self, latency_ms: float, success: bool) -> None:
        self.request_count += 1
        if not success:
            self.error_count += 1
        self.error_rate = self.error_count / max(self.request_count, 1)
        self.latency_samples_ms.append(float(latency_ms))
        samples = sorted(self.latency_samples_ms)
        self.latency_p95_ms = samples[min(len(samples) - 1, int(round((len(samples) - 1) * 0.95)))]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("latency_samples_ms", None)
        data["ready"] = self.ready
        return data
