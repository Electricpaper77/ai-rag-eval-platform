from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.job_orchestrator as job_orchestrator
import gpu_platform.runtime_backends as runtime_backends

client = TestClient(app)


def _set_paths(tmp_path: Path, monkeypatch) -> Path:
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

    monkeypatch.setattr(runtime_backends, "PLATFORM_RUNTIME_ARTIFACTS_DIR", base)
    monkeypatch.setattr(runtime_backends, "RUNTIME_SELECTIONS_PATH", base / "runtime_selections.jsonl")
    monkeypatch.setattr(runtime_backends, "RUNTIME_VALIDATION_RESULTS_PATH", base / "runtime_validation_results.jsonl")
    monkeypatch.setattr(runtime_backends, "VLLM_RUNTIME_CONFIGS_PATH", base / "vllm_runtime_configs.jsonl")
    monkeypatch.setattr(runtime_backends, "RUNTIME_DEPLOYMENTS_PATH", base / "runtime_deployments.jsonl")
    return base


def _payload() -> dict:
    return {
        "workload_type": "inference",
        "image": "vllm/vllm-openai:latest",
        "model": "meta-llama/Llama-3-8B-Instruct",
        "gpu_count": 4,
        "cpu": "4",
        "memory": "16Gi",
        "priority_class": "latency-sensitive",
        "tensor_parallel": 2,
        "pipeline_parallel": 1,
        "data_parallel": 1,
        "replicas": 1,
        "gpu_per_replica": 4,
    }


def test_vllm_runtime_config_generation(tmp_path: Path, monkeypatch) -> None:
    base = _set_paths(tmp_path, monkeypatch)
    body = client.post("/platform/jobs", json=_payload()).json()
    assert body["runtime"]["runtime_name"] == "vllm"

    config_file = base / "vllm_runtime_configs.jsonl"
    deployment_file = base / "runtime_deployments.jsonl"
    assert config_file.exists()
    assert deployment_file.exists()

    config = json.loads(config_file.read_text(encoding="utf-8").splitlines()[-1])
    assert config["tensor_parallel_size"] == 2
    assert config["runtime_name"] == "vllm"


def test_runtime_fallback_behavior(tmp_path: Path, monkeypatch) -> None:
    _set_paths(tmp_path, monkeypatch)
    payload = _payload()
    payload["distributed_executor_backend"] = "bad-executor"

    body = client.post("/platform/jobs", json=payload).json()
    assert body["runtime"]["runtime_name"] == "mock"


def test_runtime_selection_latency_sensitive_prefers_vllm(tmp_path: Path, monkeypatch) -> None:
    _set_paths(tmp_path, monkeypatch)
    payload = _payload()
    payload["tensor_parallel"] = 1

    body = client.post("/platform/jobs", json=payload).json()
    assert body["runtime"]["runtime_name"] == "vllm"


def test_distributed_workload_chooses_vllm(tmp_path: Path, monkeypatch) -> None:
    _set_paths(tmp_path, monkeypatch)
    payload = _payload()
    payload["priority_class"] = "balanced"
    payload["tensor_parallel"] = 2
    payload["pipeline_parallel"] = 2

    body = client.post("/platform/jobs", json=payload).json()
    assert body["runtime"]["runtime_name"] == "vllm"


def test_invalid_runtime_config_returns_reason_code(tmp_path: Path, monkeypatch) -> None:
    base = _set_paths(tmp_path, monkeypatch)
    payload = _payload()
    payload["gpu_count"] = 1
    payload["gpu_per_replica"] = 1
    payload["tensor_parallel"] = 4

    body = client.post("/platform/jobs", json=payload).json()
    assert "inconsistent_parallelism" in body["runtime"]["validation"]["reason_codes"]

    validation_file = base / "runtime_validation_results.jsonl"
    validation = json.loads(validation_file.read_text(encoding="utf-8").splitlines()[-1])
    assert "reason_codes" in validation


def test_additive_schema_compatibility_with_platform_jobs(tmp_path: Path, monkeypatch) -> None:
    _set_paths(tmp_path, monkeypatch)
    body = client.post("/platform/jobs", json=_payload()).json()

    assert body["job_id"]
    assert body["status"] in {"succeeded", "failed"}
    assert "routing" in body
    assert "runtime" in body
    assert "runtime_name" in body["runtime"]
    assert "runtime_plan" in body["runtime"]
