from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.benchmark_summary as benchmark_summary
import gpu_platform.job_orchestrator as job_orchestrator


client = TestClient(app)


def _set_store_paths(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "artifacts" / "platform"
    jobs_base = tmp_path / "artifacts" / "platform_jobs"
    base = tmp_path / "artifacts" / "platform_jobs"
    monkeypatch.setattr(job_orchestrator, "PLATFORM_ARTIFACTS_DIR", base)
    monkeypatch.setattr(job_orchestrator, "JOBS_FILE", base / "jobs.jsonl")
    monkeypatch.setattr(job_orchestrator, "PREFLIGHT_FILE", base / "preflight_results.jsonl")
    monkeypatch.setattr(job_orchestrator, "DISTRIBUTED_FILE", base / "distributed_jobs.jsonl")
    monkeypatch.setattr(job_orchestrator, "SLURM_FILE", base / "slurm_submissions.jsonl")
    monkeypatch.setattr(job_orchestrator, "PLATFORM_JOB_ARTIFACTS_DIR", jobs_base)
    monkeypatch.setattr(job_orchestrator, "DISTRIBUTED_JOBS_FILE", jobs_base / "distributed_jobs.jsonl")
    monkeypatch.setattr(job_orchestrator, "ADMISSION_REJECTIONS_FILE", jobs_base / "admission_rejections.jsonl")
    monkeypatch.setattr(job_orchestrator, "POSTMORTEM_FILE", base / "postmortem_reports.jsonl")


def _metric_value(metrics_payload: str, metric_name: str) -> float:
    for line in metrics_payload.splitlines():
        if line.startswith(metric_name):
            try:
                return float(line.split()[-1])
            except ValueError:
                continue
    raise AssertionError(f"Metric not found: {metric_name}")


def _valid_payload() -> dict:
    return {
        "workload_type": "inference",
        "image": "nvcr.io/nvidia/tritonserver:24.01-py3",
        "model": "llama-3-8b",
        "gpu_count": 1,
        "cpu": "4",
        "memory": "16Gi",
        "pvc_size": "100Gi",
        "storage_class": "fast-ssd",
        "node_selector": {"accelerator": "nvidia"},
        "tolerations": [{"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"}],
        "env": {"MODEL_CACHE": "/models"},
        "command": ["python", "serve.py"],
        "retry_limit": 1,
        "mount_path": "/models",
        "readiness_probe": {"httpGet": {"path": "/healthz", "port": 8080}},
        "liveness_probe": {"httpGet": {"path": "/livez", "port": 8080}},
        "network_isolation": {"policy": "default-deny"},
    }


def test_platform_metrics_exposed_and_incremented(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)

    mock_summary_path = tmp_path / "distributed_benchmark_summary.json"
    mock_summary_path.write_text(
        json.dumps({"runs": [{"run_id": "run-001", "p95_latency_ms": 123.4, "tokens_per_sec": 456.7}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(benchmark_summary, "SUMMARY_PATH", mock_summary_path)

    before_metrics = client.get("/metrics")
    assert before_metrics.status_code == 200

    before_submitted = _metric_value(before_metrics.text, "platform_jobs_submitted_total")

    create_resp = client.post("/platform/jobs", json=_valid_payload())
    assert create_resp.status_code == 200

    summary_resp = client.get("/platform/benchmark-summary")
    assert summary_resp.status_code == 200

    after_metrics = client.get("/metrics")
    assert after_metrics.status_code == 200

    assert _metric_value(after_metrics.text, "platform_jobs_submitted_total") >= before_submitted + 1
    assert _metric_value(after_metrics.text, "platform_job_duration_seconds_count") >= 1
    assert _metric_value(after_metrics.text, "platform_queue_depth") >= 0
    assert _metric_value(after_metrics.text, "platform_distributed_jobs_total") >= 1
    assert _metric_value(after_metrics.text, 'platform_priority_queue_depth{priority_class="balanced"}') >= 0
    assert _metric_value(after_metrics.text, "platform_parallelism_config_total") >= 1
    assert _metric_value(after_metrics.text, "benchmark_latency_p95_ms") == 123.4
    assert _metric_value(after_metrics.text, "benchmark_tokens_per_sec") == 456.7
