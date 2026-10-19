from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from prometheus_client import Counter, Gauge, Histogram

from .models import FAULT_TYPES, FaultState


ACTIVE_CHAOS_FAULT = Gauge("agenttrust_active_chaos_fault", "Active Gate 10 fault", ["fault_type"])
EXPERIMENTS_TOTAL = Counter("agenttrust_resilience_experiments_total", "Gate 10 experiments", ["fault_type", "result"])
RECOVERY_TOTAL = Counter("agenttrust_resilience_recovery_total", "Recovered Gate 10 faults", ["fault_type"])
DEPENDENCY_FAILURES_TOTAL = Counter("agenttrust_resilience_dependency_failures_total", "Dependency failures observed")
ERROR_BUDGET_CONSUMED = Gauge("agenttrust_resilience_error_budget_consumed_percent", "CI resilience error budget consumed")
RECOVERY_DURATION_SECONDS = Histogram("agenttrust_resilience_recovery_duration_seconds", "Gate 10 recovery duration", ["fault_type"])


class FaultInjectionDisabled(RuntimeError):
    pass


class ResilienceController:
    MAX_DURATION_SECONDS = 120.0

    def __init__(self) -> None:
        self._active: FaultState | None = None
        self._active_until = 0.0
        self._history: list[FaultState] = []
        self._sync_metrics()

    @property
    def enabled(self) -> bool:
        return os.getenv("GATE10_ENABLE_FAULTS", "0").lower() in {"1", "true", "yes"}

    def _sync_metrics(self) -> None:
        for fault_type in FAULT_TYPES:
            ACTIVE_CHAOS_FAULT.labels(fault_type).set(1 if self._active and self._active.fault_type == fault_type else 0)

    def _expire_if_needed(self) -> None:
        if self._active and time.monotonic() >= self._active_until:
            expired = FaultState(**{**self._active.as_dict(), "recovery_state": "recovered"})
            self._history.append(expired)
            RECOVERY_TOTAL.labels(expired.fault_type).inc()
            RECOVERY_DURATION_SECONDS.labels(expired.fault_type).observe(expired.duration_seconds)
            self._active = None
            self._active_until = 0.0
            self._sync_metrics()

    def status(self) -> dict[str, Any]:
        self._expire_if_needed()
        return {
            "enabled": self.enabled,
            "active": self._active.as_dict() if self._active else None,
            "history": [item.as_dict() for item in self._history[-20:]],
            "fault_types": list(FAULT_TYPES),
        }

    def faults(self) -> dict[str, Any]:
        return {"fault_types": list(FAULT_TYPES), "enabled": self.enabled}

    def is_active(self, fault_type: str) -> bool:
        self._expire_if_needed()
        return bool(self._active and self._active.fault_type == fault_type)

    def inject(self, fault_type: str, *, duration_seconds: float = 10.0, affected_component: str = "gate10-serving") -> dict[str, Any]:
        self._expire_if_needed()
        if not self.enabled:
            raise FaultInjectionDisabled("Gate 10 fault injection is disabled")
        if fault_type not in FAULT_TYPES:
            raise ValueError(f"unsupported fault type: {fault_type}")
        duration = min(max(float(duration_seconds), 0.1), self.MAX_DURATION_SECONDS)
        if self._active:
            raise ValueError("another fault is already active")
        state = FaultState(
            fault_type=fault_type,
            started_at=datetime.now(UTC).isoformat(),
            duration_seconds=duration,
            affected_component=affected_component,
        )
        self._active = state
        self._active_until = time.monotonic() + duration
        EXPERIMENTS_TOTAL.labels(fault_type, "injected").inc()
        self._sync_metrics()
        return state.as_dict()

    def recover(self) -> dict[str, Any]:
        self._expire_if_needed()
        if not self._active:
            return {"recovered": True, "active": None}
        state = FaultState(**{**self._active.as_dict(), "recovery_state": "recovered"})
        self._history.append(state)
        RECOVERY_TOTAL.labels(state.fault_type).inc()
        RECOVERY_DURATION_SECONDS.labels(state.fault_type).observe(max(0.0, state.duration_seconds))
        self._active = None
        self._active_until = 0.0
        self._sync_metrics()
        return {"recovered": True, "active": None, "fault": state.as_dict()}


DEFAULT_CONTROLLER = ResilienceController()
router = APIRouter(prefix="/platform/resilience", tags=["resilience"])


@router.get("/status")
def resilience_status() -> dict[str, Any]:
    return DEFAULT_CONTROLLER.status()


@router.get("/faults")
def resilience_faults() -> dict[str, Any]:
    return DEFAULT_CONTROLLER.faults()


@router.post("/inject")
def resilience_inject(request: dict[str, Any]) -> dict[str, Any]:
    try:
        return DEFAULT_CONTROLLER.inject(
            str(request.get("fault_type", "")),
            duration_seconds=float(request.get("duration_seconds", 10.0)),
            affected_component=str(request.get("affected_component", "gate10-serving")),
        )
    except FaultInjectionDisabled as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/recover")
def resilience_recover() -> dict[str, Any]:
    return DEFAULT_CONTROLLER.recover()
