from __future__ import annotations

import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app.main import app
from backend.app.reliability_engineering import (
    DistributedBenchmarkSimulator,
    IncidentSimulator,
    ReliabilityMetrics,
    SLOTracker,
)


def test_slo_tracker_exports_json(tmp_path: Path) -> None:
    tracker = SLOTracker(latency_objective_ms=900, availability_objective=0.98)
    tracker.observe(200, success=True)
    tracker.observe(400, success=True)
    tracker.observe(1500, success=False, retries=1, timed_out=True)

    output = tmp_path / "slo.json"
    tracker.export_json(output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["slo"]["latency_objective_ms"] == 900
    assert payload["observed"]["error_rate"] > 0
    assert payload["observed"]["timeout_count"] == 1


def test_incident_simulator_generates_postmortem(tmp_path: Path) -> None:
    simulator = IncidentSimulator(seed=2)
    output = tmp_path / "postmortem.json"
    simulator.export_postmortem_json("model_failure", output_path=output, requests=60)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["incident_type"] == "model_failure"
    assert payload["postmortem"]["mitigations"]
    assert payload["timeline"]


def test_distributed_benchmark_simulation_json(tmp_path: Path) -> None:
    simulator = DistributedBenchmarkSimulator(seed=3)
    output = tmp_path / "distributed.json"
    simulator.export_json(output_path=output, samples_per_runtime=25)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["runs"]) == 3
    assert payload["runs"][0]["latency_distribution_ms"]["p95"] >= payload["runs"][0]["latency_distribution_ms"]["p50"]


def test_reliability_metrics_rate_fields() -> None:
    metrics = ReliabilityMetrics()
    metrics.record_request(success=True)
    metrics.record_request(success=False, retries=2, timed_out=True)

    values = metrics.as_dict()
    assert values["retry_count"] == 2
    assert values["timeout_count"] == 1
    assert values["error_rate"] == 0.5
    assert values["success_rate"] == 0.5


def test_prometheus_metrics_exposed() -> None:
    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "reliability_requests_total" in body
    assert "distributed_runtime_queue_depth" in body
