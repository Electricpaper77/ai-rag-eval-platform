from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
from gpu_platform.gpu_job import GPUJobSpec
from gpu_platform.job_manager import get_job_status, submit_job
from gpu_platform.preflight_checks import run_preflight_checks
import gpu_platform.job_manager as job_manager


client = TestClient(app)


def _set_store_paths(tmp_path: Path, monkeypatch) -> Path:
    jobs_dir = tmp_path / "artifacts" / "platform_jobs"
    status_file = jobs_dir / "job_status.json"
    monkeypatch.setattr(job_manager, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(job_manager, "STATUS_FILE", status_file)
    return status_file


def test_preflight_validation_failures() -> None:
    invalid = GPUJobSpec(
        job_id="bad-job",
        model_name="mistral-7b",
        gpu_count=0,
        replicas=0,
        container_image="not valid image",
        env={},
        resources={},
    )

    result = run_preflight_checks(invalid)
    assert result["status"] == "fail"
    assert result["errors"]


def test_job_submission_and_status_transitions(tmp_path: Path, monkeypatch) -> None:
    status_file = _set_store_paths(tmp_path, monkeypatch)

    now = 1000.0
    monkeypatch.setattr(job_manager.time, "time", lambda: now)

    spec = GPUJobSpec(
        job_id="eval-benchmark-001",
        model_name="mistral-7b",
        gpu_count=1,
        replicas=1,
        container_image="vllm/vllm-openai:latest",
        env={"ENV": "test"},
        resources={"limits": {"nvidia.com/gpu": 1}},
    )

    submitted = submit_job(spec)
    assert submitted["status"] == "pending"
    assert status_file.exists()

    payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert "eval-benchmark-001" in payload["jobs"]

    now = 1001.2
    running = get_job_status("eval-benchmark-001")
    assert running is not None
    assert running["status"] == "running"

    now = 1002.6
    completed = get_job_status("eval-benchmark-001")
    assert completed is not None
    assert completed["status"] == "completed"


def test_health_check_fields_present(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)

    spec = GPUJobSpec(
        job_id="eval-benchmark-002",
        model_name="mistral-7b",
        gpu_count=1,
        replicas=1,
        container_image="vllm/vllm-openai:latest",
        env={},
        resources={"limits": {"nvidia.com/gpu": 1}},
    )
    submit_job(spec)
    job = get_job_status("eval-benchmark-002")

    assert job is not None
    health = job["health"]
    assert "startup_latency_ms" in health
    assert "readiness_status" in health
    assert "gpu_allocated" in health


def test_platform_api_endpoints_respond(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)

    create_resp = client.post(
        "/platform/jobs",
        json={
            "job_id": "eval-benchmark-003",
            "model_name": "mistral-7b",
            "gpu_count": 1,
            "replicas": 1,
            "container_image": "vllm/vllm-openai:latest",
            "env": {"MODE": "test"},
            "resources": {"limits": {"nvidia.com/gpu": 1}},
        },
    )
    assert create_resp.status_code == 200

    list_resp = client.get("/platform/jobs")
    assert list_resp.status_code == 200
    assert any(job["job_id"] == "eval-benchmark-003" for job in list_resp.json())

    detail_resp = client.get("/platform/jobs/eval-benchmark-003")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["job_id"] == "eval-benchmark-003"
