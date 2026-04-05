from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.job_status as job_status
from gpu_platform.model_policy import select_model_by_policy


client = TestClient(app)


def test_model_policy_fallback_when_unhealthy() -> None:
    decision = select_model_by_policy(
        latency_budget_ms=400,
        quality_tier="premium",
        cost_priority="balanced",
        model_health_status={"vllm": "unhealthy", "openai": "unhealthy", "mock": "healthy"},
    )
    assert decision["selected_model"] == "mock"


def test_platform_summary_endpoint_aggregates_job_logs(tmp_path: Path, monkeypatch) -> None:
    log_path = tmp_path / "artifacts" / "platform_jobs" / "job_runs.jsonl"
    monkeypatch.setattr(job_status, "JOB_RUNS_PATH", log_path)
    monkeypatch.setattr(job_status, "BENCHMARK_ARTIFACT_PATHS", tuple())

    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"job_id": "a", "model_used": "vllm", "latency_ms": 100.0, "success": True, "timestamp": "2026-04-05T00:00:00+00:00"},
        {"job_id": "b", "model_used": "mock", "latency_ms": 300.0, "success": False, "timestamp": "2026-04-05T00:00:01+00:00"},
    ]
    with log_path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row) + "\n")

    resp = client.get("/platform/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["avg_latency_ms"] == 200.0
    assert body["success_rate"] == 0.5
    assert body["total_jobs_run"] == 2
