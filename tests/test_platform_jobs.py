from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.job_orchestrator as job_orchestrator


client = TestClient(app)


def _set_store_paths(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "artifacts" / "platform"
    monkeypatch.setattr(job_orchestrator, "PLATFORM_ARTIFACTS_DIR", base)
    monkeypatch.setattr(job_orchestrator, "JOBS_FILE", base / "jobs.jsonl")
    monkeypatch.setattr(job_orchestrator, "PREFLIGHT_FILE", base / "preflight_results.jsonl")
    monkeypatch.setattr(job_orchestrator, "SLURM_FILE", base / "slurm_submissions.jsonl")


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
        "retries": 1,
    }


def test_submit_job_creates_platform_artifacts(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)

    job = job_orchestrator.submit_job(_valid_payload())
    assert job["status"] == "succeeded"

    assert (tmp_path / "artifacts" / "platform" / "jobs.jsonl").exists()
    assert (tmp_path / "artifacts" / "platform" / "preflight_results.jsonl").exists()
    assert (tmp_path / "artifacts" / "platform" / "slurm_submissions.jsonl").exists()


def test_platform_api_job_endpoints(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)

    create_resp = client.post("/platform/jobs", json=_valid_payload())
    assert create_resp.status_code == 200
    job_id = create_resp.json()["job_id"]

    list_resp = client.get("/platform/jobs")
    assert list_resp.status_code == 200
    jobs = list_resp.json()
    assert any(job["job_id"] == job_id for job in jobs)

    detail_resp = client.get(f"/platform/jobs/{job_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["job_id"] == job_id


def test_preflight_fail_path(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)

    invalid = _valid_payload()
    invalid["image"] = ""
    invalid["gpu_count"] = 0

    create_resp = client.post("/platform/jobs", json=invalid)
    assert create_resp.status_code == 200
    assert create_resp.json()["status"] == "failed"
