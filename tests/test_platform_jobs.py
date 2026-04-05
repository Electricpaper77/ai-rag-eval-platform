from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.job_orchestrator as job_orchestrator


client = TestClient(app)


def _set_store_paths(tmp_path: Path, monkeypatch) -> None:
    jobs_dir = tmp_path / "artifacts" / "job_runs"
    monkeypatch.setattr(job_orchestrator, "JOB_RUNS_DIR", jobs_dir)


def test_submit_job_creates_structured_artifact(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)

    job_id = job_orchestrator.submit_job(
        model="llm-balanced",
        dataset="eval_dataset_v2",
        runtime="vllm",
        gpu_required=True,
    )

    job_path = (tmp_path / "artifacts" / "job_runs" / f"{job_id}.json")
    assert job_path.exists()

    job = job_orchestrator.get_job(job_id)
    assert job is not None
    assert job["job_id"] == job_id
    assert job["dataset"] == "eval_dataset_v2"
    assert job["runtime"] == "vllm"
    assert "latency_summary" in job


def test_platform_api_job_endpoints(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)

    create_resp = client.post(
        "/platform/jobs",
        json={
            "model": "llm-balanced",
            "dataset": "eval_dataset_v2",
            "runtime": "vllm",
            "gpu_required": True,
        },
    )
    assert create_resp.status_code == 200
    job_id = create_resp.json()["job_id"]

    list_resp = client.get("/platform/jobs")
    assert list_resp.status_code == 200
    jobs = list_resp.json()
    assert any(job["job_id"] == job_id for job in jobs)

    detail_resp = client.get(f"/platform/jobs/{job_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["job_id"] == job_id


def test_get_missing_job_returns_none(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)
    assert job_orchestrator.get_job("job_999") is None
