from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.benchmark_summary as benchmark_summary
import gpu_platform.job_manager as job_manager


client = TestClient(app)


def _set_store_paths(tmp_path: Path, monkeypatch) -> None:
    jobs_dir = tmp_path / "artifacts" / "platform_jobs"
    status_file = jobs_dir / "job_status.json"
    monkeypatch.setattr(job_manager, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(job_manager, "STATUS_FILE", status_file)


def _metric_value(metrics_payload: str, metric_name: str) -> float:
    for line in metrics_payload.splitlines():
        if line.startswith(metric_name):
            try:
                return float(line.split()[-1])
            except ValueError:
                continue
    raise AssertionError(f"Metric not found: {metric_name}")


def test_platform_metrics_exposed_and_incremented(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)

    mock_summary_path = tmp_path / "distributed_benchmark_summary.json"
    mock_summary_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "run-001",
                        "model": "mistral-7b",
                        "gpu_count": 1,
                        "batch_size": 4,
                        "p95_latency_ms": 123.4,
                        "tokens_per_sec": 456.7,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(benchmark_summary, "SUMMARY_PATH", mock_summary_path)

    before_metrics = client.get("/metrics")
    assert before_metrics.status_code == 200

    before_submitted = _metric_value(before_metrics.text, "gpu_jobs_submitted_total")
    before_completed = _metric_value(before_metrics.text, "gpu_jobs_completed_total")
    before_hist_count = _metric_value(before_metrics.text, "gpu_job_duration_seconds_count")
    before_runs = _metric_value(before_metrics.text, "benchmark_runs_total")

    now = {"value": 1000.0}
    monkeypatch.setattr(job_manager.time, "time", lambda: now["value"])

    create_resp = client.post(
        "/platform/jobs",
        json={
            "job_id": "metrics-job-001",
            "model_name": "mistral-7b",
            "gpu_count": 1,
            "replicas": 1,
            "container_image": "vllm/vllm-openai:latest",
            "env": {"MODE": "test"},
            "resources": {"limits": {"nvidia.com/gpu": 1}},
        },
    )
    assert create_resp.status_code == 200

    now["value"] = 1003.0
    client.get("/platform/jobs/metrics-job-001")

    summary_resp = client.get("/platform/benchmark-summary")
    assert summary_resp.status_code == 200

    after_metrics = client.get("/metrics")
    assert after_metrics.status_code == 200

    assert _metric_value(after_metrics.text, "gpu_jobs_submitted_total") >= before_submitted + 1
    assert _metric_value(after_metrics.text, "gpu_jobs_completed_total") >= before_completed + 1
    assert _metric_value(after_metrics.text, "gpu_job_duration_seconds_count") >= before_hist_count + 1
    assert _metric_value(after_metrics.text, "benchmark_runs_total") >= before_runs + 1
    assert _metric_value(after_metrics.text, "benchmark_latency_p95_ms") == 123.4
    assert _metric_value(after_metrics.text, "benchmark_tokens_per_sec") == 456.7
