from __future__ import annotations

import json
import random
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .metrics import (
    record_distributed_runtime_metrics,
    record_reliability_metrics,
)


@dataclass
class ReliabilityMetrics:
    total_requests: int = 0
    error_count: int = 0
    retry_count: int = 0
    timeout_count: int = 0
    success_count: int = 0

    def record_request(self, *, success: bool, retries: int = 0, timed_out: bool = False) -> None:
        self.total_requests += 1
        self.retry_count += max(retries, 0)

        if timed_out:
            self.timeout_count += 1

        if success:
            self.success_count += 1
            status = "success"
        else:
            self.error_count += 1
            status = "error"

        record_reliability_metrics(
            status=status,
            retries=max(retries, 0),
            timed_out=timed_out,
            total_requests=self.total_requests,
            error_count=self.error_count,
            success_count=self.success_count,
        )

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.error_count / self.total_requests, 6)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.success_count / self.total_requests, 6)

    def as_dict(self) -> dict[str, float | int]:
        return {
            "error_rate": self.error_rate,
            "retry_count": self.retry_count,
            "timeout_count": self.timeout_count,
            "success_rate": self.success_rate,
            "total_requests": self.total_requests,
        }


@dataclass
class SLOTracker:
    latency_objective_ms: float
    availability_objective: float
    latencies_ms: list[float] = field(default_factory=list)
    reliability: ReliabilityMetrics = field(default_factory=ReliabilityMetrics)

    def observe(self, latency_ms: float, *, success: bool, retries: int = 0, timed_out: bool = False) -> None:
        bounded_latency = max(float(latency_ms), 0.0)
        self.latencies_ms.append(bounded_latency)
        self.reliability.record_request(success=success, retries=retries, timed_out=timed_out)

    def summary(self) -> dict[str, Any]:
        if not self.latencies_ms:
            p95_latency = 0.0
            avg_latency = 0.0
        else:
            sorted_latencies = sorted(self.latencies_ms)
            p95_index = max(0, min(len(sorted_latencies) - 1, int(len(sorted_latencies) * 0.95) - 1))
            p95_latency = round(sorted_latencies[p95_index], 3)
            avg_latency = round(statistics.fmean(self.latencies_ms), 3)

        latency_slo_met = p95_latency <= self.latency_objective_ms
        availability_slo_met = self.reliability.success_rate >= self.availability_objective

        return {
            "slo": {
                "latency_objective_ms": self.latency_objective_ms,
                "availability_objective": self.availability_objective,
                "latency_slo_met": latency_slo_met,
                "availability_slo_met": availability_slo_met,
            },
            "observed": {
                "p95_latency_ms": p95_latency,
                "avg_latency_ms": avg_latency,
                **self.reliability.as_dict(),
            },
            "sample_size": len(self.latencies_ms),
        }

    def export_json(self, output_path: Path) -> Path:
        payload = {
            "generated_at_epoch_s": int(time.time()),
            **self.summary(),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return output_path


class IncidentSimulator:
    def __init__(self, seed: int = 7) -> None:
        self._random = random.Random(seed)

    def simulate(self, incident_type: str, requests: int = 120) -> dict[str, Any]:
        if incident_type not in {"latency_spike", "model_failure"}:
            raise ValueError("incident_type must be 'latency_spike' or 'model_failure'")

        tracker = SLOTracker(latency_objective_ms=800.0, availability_objective=0.99)
        timeline: list[dict[str, Any]] = []

        for idx in range(requests):
            if incident_type == "latency_spike":
                latency_ms = self._random.uniform(1200, 2800) if 30 <= idx <= 75 else self._random.uniform(150, 450)
                success = self._random.random() > 0.015
                timed_out = latency_ms > 2200
                retries = 1 if timed_out else 0
            else:
                failure_window = 40 <= idx <= 90
                latency_ms = self._random.uniform(250, 900)
                success = not (failure_window and self._random.random() < 0.45)
                timed_out = False
                retries = 2 if not success else 0

            tracker.observe(latency_ms, success=success, retries=retries, timed_out=timed_out)
            timeline.append(
                {
                    "request_id": idx + 1,
                    "latency_ms": round(latency_ms, 2),
                    "success": success,
                    "timed_out": timed_out,
                    "retries": retries,
                }
            )

        summary = tracker.summary()
        return {
            "incident_type": incident_type,
            "impact": {
                "duration_requests": requests,
                "error_rate": summary["observed"]["error_rate"],
                "success_rate": summary["observed"]["success_rate"],
                "p95_latency_ms": summary["observed"]["p95_latency_ms"],
            },
            "slo_breach": {
                "latency": not summary["slo"]["latency_slo_met"],
                "availability": not summary["slo"]["availability_slo_met"],
            },
            "postmortem": {
                "root_cause": "runtime saturation" if incident_type == "latency_spike" else "model backend instability",
                "mitigations": [
                    "Enable adaptive concurrency limits",
                    "Introduce circuit-breaker + fallback runtime",
                    "Improve canary guardrails before full rollout",
                ],
            },
            "timeline": timeline,
        }

    def export_postmortem_json(self, incident_type: str, output_path: Path, requests: int = 120) -> Path:
        payload = self.simulate(incident_type=incident_type, requests=requests)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return output_path


class DistributedBenchmarkSimulator:
    def __init__(self, runtimes: list[str] | None = None, seed: int = 17) -> None:
        self.runtimes = runtimes or ["vllm", "triton", "openai_compat"]
        if len(self.runtimes) != 3:
            raise ValueError("Exactly 3 runtimes are required for distributed benchmark simulation")
        self._random = random.Random(seed)

    def run(self, samples_per_runtime: int = 100) -> dict[str, Any]:
        runs: list[dict[str, Any]] = []

        for runtime in self.runtimes:
            latency_samples = [round(self._random.uniform(120, 900), 2) for _ in range(samples_per_runtime)]
            queue_samples = [self._random.randint(0, 32) for _ in range(samples_per_runtime)]

            latency_sorted = sorted(latency_samples)
            p50 = latency_sorted[int(0.50 * (samples_per_runtime - 1))]
            p95 = latency_sorted[int(0.95 * (samples_per_runtime - 1))]
            queue_depth_avg = round(statistics.fmean(queue_samples), 3)

            for latency, queue_depth in zip(latency_samples, queue_samples, strict=True):
                record_distributed_runtime_metrics(runtime=runtime, queue_depth=queue_depth, latency_ms=latency)

            runs.append(
                {
                    "runtime": runtime,
                    "queue_depth": {
                        "avg": queue_depth_avg,
                        "max": max(queue_samples),
                    },
                    "latency_distribution_ms": {
                        "p50": round(p50, 2),
                        "p95": round(p95, 2),
                        "min": min(latency_samples),
                        "max": max(latency_samples),
                    },
                    "samples": samples_per_runtime,
                }
            )

        return {
            "generated_at_epoch_s": int(time.time()),
            "runs": runs,
        }

    def export_json(self, output_path: Path, samples_per_runtime: int = 100) -> Path:
        payload = self.run(samples_per_runtime=samples_per_runtime)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return output_path
