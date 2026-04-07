from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.request_router as request_router
import gpu_platform.job_orchestrator as job_orchestrator


client = TestClient(app)


def _configure_paths(tmp_path: Path, monkeypatch) -> Path:
    decisions_path = tmp_path / "artifacts" / "platform_jobs" / "routing_decisions.jsonl"
    monkeypatch.setattr(request_router, "ROUTING_DECISIONS_PATH", decisions_path)

    base = tmp_path / "artifacts" / "platform_jobs"
    monkeypatch.setattr(job_orchestrator, "PLATFORM_ARTIFACTS_DIR", base)
    monkeypatch.setattr(job_orchestrator, "JOBS_FILE", base / "jobs.jsonl")
    monkeypatch.setattr(job_orchestrator, "PREFLIGHT_FILE", base / "preflight_results.jsonl")
    monkeypatch.setattr(job_orchestrator, "DISTRIBUTED_FILE", base / "distributed_jobs.jsonl")
    monkeypatch.setattr(job_orchestrator, "SLURM_FILE", base / "slurm_submissions.jsonl")
    monkeypatch.setattr(job_orchestrator, "PLATFORM_JOB_ARTIFACTS_DIR", base)
    monkeypatch.setattr(job_orchestrator, "DISTRIBUTED_JOBS_FILE", base / "distributed_jobs.jsonl")
    monkeypatch.setattr(job_orchestrator, "ADMISSION_REJECTIONS_FILE", base / "admission_rejections.jsonl")
    monkeypatch.setattr(job_orchestrator, "POSTMORTEM_FILE", base / "postmortem_reports.jsonl")
    return decisions_path


def _valid_payload() -> dict:
    return {
        "workload_type": "inference",
        "image": "nvcr.io/nvidia/tritonserver:24.01-py3",
        "model": "llama-3-8b",
        "gpu_count": 1,
        "cpu": "4",
        "memory": "16Gi",
        "priority_class": "balanced",
        "env": {},
        "command": ["python", "serve.py"],
    }


def test_routing_is_deterministic_for_same_inputs(tmp_path: Path, monkeypatch) -> None:
    _configure_paths(tmp_path, monkeypatch)

    first = request_router.route_request(
        workload_type="inference",
        latency_budget_ms=800,
        priority_class="latency-sensitive",
        gpu_required=True,
        parallelism_config={"tensor_parallel": 1, "pipeline_parallel": 1, "data_parallel": 1},
        request_id="route-001",
        queue_depth=2,
        historical_failure_rate=0.01,
    )
    second = request_router.route_request(
        workload_type="inference",
        latency_budget_ms=800,
        priority_class="latency-sensitive",
        gpu_required=True,
        parallelism_config={"tensor_parallel": 1, "pipeline_parallel": 1, "data_parallel": 1},
        request_id="route-001",
        queue_depth=2,
        historical_failure_rate=0.01,
    )

    assert first["selected_runtime"] == second["selected_runtime"]
    assert first["gpu_pool"] == second["gpu_pool"]
    assert first["kv_cache_strategy"] == second["kv_cache_strategy"]


def test_priority_class_influences_pool_selection(tmp_path: Path, monkeypatch) -> None:
    _configure_paths(tmp_path, monkeypatch)

    latency = request_router.route_request(
        workload_type="inference",
        latency_budget_ms=850,
        priority_class="latency-sensitive",
        gpu_required=True,
        parallelism_config={"tensor_parallel": 1, "pipeline_parallel": 1, "data_parallel": 1},
        request_id="priority-latency",
    )
    batch = request_router.route_request(
        workload_type="batch",
        latency_budget_ms=2500,
        priority_class="batch",
        gpu_required=True,
        parallelism_config={"tensor_parallel": 1, "pipeline_parallel": 1, "data_parallel": 1},
        request_id="priority-batch",
    )

    assert latency["gpu_pool"] == "latency_pool"
    assert batch["gpu_pool"] == "throughput_pool"


def test_distributed_workload_selects_distributed_pool(tmp_path: Path, monkeypatch) -> None:
    decisions_path = _configure_paths(tmp_path, monkeypatch)

    distributed = request_router.route_request(
        workload_type="inference",
        latency_budget_ms=1500,
        priority_class="balanced",
        gpu_required=True,
        parallelism_config={"tensor_parallel": 4, "pipeline_parallel": 1, "data_parallel": 2, "context_tokens": 8192},
        request_id="distributed-001",
    )

    assert distributed["gpu_pool"] == "distributed_pool"
    assert distributed["kv_cache_strategy"] == "distributed"
    assert decisions_path.exists()


def test_job_response_contains_routing_and_metrics_are_exposed(tmp_path: Path, monkeypatch) -> None:
    _configure_paths(tmp_path, monkeypatch)

    response = client.post("/platform/jobs", json=_valid_payload())
    assert response.status_code == 200
    body = response.json()
    assert "routing" in body
    assert body["routing"]["gpu_pool"]
    assert body["routing"]["runtime"]
    assert body["routing"]["kv_cache_strategy"]

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "platform_routing_decisions_total" in metrics.text
    assert "platform_routing_latency_bucket" in metrics.text
    assert "platform_kv_cache_strategy_total" in metrics.text
    assert "platform_gpu_pool_selection_total" in metrics.text
