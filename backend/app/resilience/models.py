from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class FaultType(StrEnum):
    POD_DELETE = "pod_delete"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    LATENCY = "latency"
    HTTP_5XX = "http_5xx"
    READINESS_FAILURE = "readiness_failure"
    NETWORK_DENIAL = "network_denial"


FAULT_TYPES = tuple(item.value for item in FaultType)


@dataclass(frozen=True)
class FaultState:
    fault_type: str
    started_at: str
    duration_seconds: float
    affected_component: str
    detected_state: str = "injected"
    recovery_state: str = "pending"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
