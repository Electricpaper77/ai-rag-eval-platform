from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from statistics import quantiles
from typing import Any

from gpu_platform.canary_policy import CanaryPolicy

CANARY_DECISIONS_PATH = Path("artifacts/platform_jobs/canary_decisions.jsonl")
CANARY_SUMMARY_PATH = Path("artifacts/proof/canary_summary.json")


class CanaryController:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._policy: CanaryPolicy | None = None
        self._rollback_reason: str | None = None
        self._rollback_triggered = False
        self._candidate_latencies: list[float] = []
        self._baseline_latencies: list[float] = []
        self._candidate_passes = 0
        self._candidate_hallucinations = 0
        self._request_count = 0

    def start(self, policy: CanaryPolicy) -> dict[str, Any]:
        with self._lock:
            self._policy = policy
            self._rollback_reason = None
            self._rollback_triggered = False
            self._candidate_latencies = []
            self._baseline_latencies = []
            self._candidate_passes = 0
            self._candidate_hallucinations = 0
            self._request_count = 0
            self._write_summary()
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            stopped = self.status()
            self._policy = None
            self._write_summary(stopped)
            return {"stopped": True, "previous": stopped}

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._policy is None:
                return {"active": False}
            return {
                "active": True,
                "policy": self._policy.model_dump(),
                "request_count": self._request_count,
                "candidate_p95_latency_ms": self._p95(self._candidate_latencies),
                "candidate_pass_rate": self._candidate_pass_rate(),
                "candidate_hallucination_rate": self._candidate_hallucination_rate(),
                "baseline_p95_latency_ms": self._p95(self._baseline_latencies),
                "rollback_triggered": self._rollback_triggered,
                "rollback_reason": self._rollback_reason,
            }

    def choose_backend(self, request_id: str) -> tuple[bool, str | None, bool]:
        with self._lock:
            if self._policy is None:
                return False, None, self._rollback_triggered
            if self._rollback_triggered:
                return True, self._policy.baseline_backend, True
            bucket = int(hashlib.sha1(request_id.encode("utf-8")).hexdigest(), 16) % 100
            if bucket < self._policy.canary_percent:
                return True, self._policy.candidate_backend, False
            return True, self._policy.baseline_backend, False

    def record_decision(
        self,
        *,
        request_id: str,
        active_backend: str,
        latency_ms: float,
        pass_outcome: bool,
        hallucination_outcome: bool,
    ) -> None:
        with self._lock:
            if self._policy is None:
                return

            self._request_count += 1
            if active_backend == self._policy.candidate_backend:
                self._candidate_latencies.append(latency_ms)
                self._candidate_passes += 1 if pass_outcome else 0
                self._candidate_hallucinations += 1 if hallucination_outcome else 0
            elif active_backend == self._policy.baseline_backend:
                self._baseline_latencies.append(latency_ms)

            self._append_decision(
                {
                    "request_id": request_id,
                    "baseline_backend": self._policy.baseline_backend,
                    "candidate_backend": self._policy.candidate_backend,
                    "active_backend": active_backend,
                    "request_count": self._request_count,
                    "candidate_p95_latency_ms": self._p95(self._candidate_latencies),
                    "candidate_pass_rate": self._candidate_pass_rate(),
                    "candidate_hallucination_rate": self._candidate_hallucination_rate(),
                    "baseline_p95_latency_ms": self._p95(self._baseline_latencies),
                }
            )

            self._check_rollback()
            self._write_summary()

    def _check_rollback(self) -> None:
        if self._policy is None or self._rollback_triggered or not self._policy.rollback_enabled:
            return

        candidate_seen = len(self._candidate_latencies)
        if candidate_seen == 0:
            return

        candidate_p95 = self._p95(self._candidate_latencies)
        candidate_pass_rate = self._candidate_pass_rate()
        candidate_hall = self._candidate_hallucination_rate()

        if candidate_p95 > self._policy.max_p95_latency_ms:
            self._rollback_triggered = True
            self._rollback_reason = "p95 latency exceeded threshold"
        elif candidate_pass_rate < self._policy.min_pass_rate:
            self._rollback_triggered = True
            self._rollback_reason = "pass rate below threshold"
        elif candidate_hall > self._policy.max_hallucination_rate:
            self._rollback_triggered = True
            self._rollback_reason = "hallucination rate exceeded threshold"

    def _candidate_pass_rate(self) -> float:
        total = len(self._candidate_latencies)
        if total == 0:
            return 0.0
        return round(self._candidate_passes / total, 4)

    def _candidate_hallucination_rate(self) -> float:
        total = len(self._candidate_latencies)
        if total == 0:
            return 0.0
        return round(self._candidate_hallucinations / total, 4)

    @staticmethod
    def _p95(values: list[float]) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return round(values[0], 2)
        return round(quantiles(values, n=100, method="inclusive")[94], 2)

    def _append_decision(self, row: dict[str, Any]) -> None:
        CANARY_DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CANARY_DECISIONS_PATH.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(row) + "\n")

    def _write_summary(self, snapshot: dict[str, Any] | None = None) -> None:
        payload = snapshot or self.status()
        summary: dict[str, Any]
        if not payload.get("active"):
            summary = {
                "rollback_triggered": bool(payload.get("rollback_triggered", False)),
                "rollback_reason": payload.get("rollback_reason"),
                "requests_evaluated": int(payload.get("request_count", 0)),
                "status": "inactive",
            }
        else:
            policy = payload["policy"]
            summary = {
                "baseline_backend": policy["baseline_backend"],
                "candidate_backend": policy["candidate_backend"],
                "canary_percent": policy["canary_percent"],
                "requests_evaluated": payload["request_count"],
                "candidate_p95_latency_ms": payload["candidate_p95_latency_ms"],
                "candidate_pass_rate": payload["candidate_pass_rate"],
                "candidate_hallucination_rate": payload["candidate_hallucination_rate"],
                "baseline_p95_latency_ms": payload["baseline_p95_latency_ms"],
                "rollback_triggered": payload["rollback_triggered"],
                "rollback_reason": payload["rollback_reason"],
            }
        CANARY_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        CANARY_SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")


CANARY_CONTROLLER = CanaryController()
