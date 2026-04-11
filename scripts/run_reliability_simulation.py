#!/usr/bin/env python3
"""Generate reliability engineering simulation artifacts."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.app.reliability_engineering import (
    DistributedBenchmarkSimulator,
    IncidentSimulator,
    SLOTracker,
)

ARTIFACT_DIR = Path("artifacts/reliability")


def build_slo_artifact() -> Path:
    tracker = SLOTracker(latency_objective_ms=800.0, availability_objective=0.99)
    samples = [210, 280, 340, 310, 520, 790, 420, 405, 390, 615]
    for latency in samples:
        tracker.observe(latency, success=True, retries=0, timed_out=False)
    tracker.observe(2300, success=False, retries=1, timed_out=True)
    return tracker.export_json(ARTIFACT_DIR / "slo_tracker.json")


def build_incident_artifact() -> Path:
    simulator = IncidentSimulator(seed=11)
    return simulator.export_postmortem_json(
        incident_type="latency_spike",
        output_path=ARTIFACT_DIR / "incident_postmortem.json",
        requests=120,
    )


def build_distributed_benchmark_artifact() -> Path:
    simulator = DistributedBenchmarkSimulator(seed=23)
    return simulator.export_json(
        output_path=ARTIFACT_DIR / "distributed_runtime_benchmark.json",
        samples_per_runtime=80,
    )


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    outputs = {
        "slo_tracker": str(build_slo_artifact()),
        "incident_postmortem": str(build_incident_artifact()),
        "distributed_benchmark": str(build_distributed_benchmark_artifact()),
    }
    print(json.dumps(outputs, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
