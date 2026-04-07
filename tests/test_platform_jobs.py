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
    jobs_base = tmp_path / "artifacts" / "platform_jobs"
    monkeypatch.setattr(job_orchestrator, "PLATFORM_ARTIFACTS_DIR", base)
    monkeypatch.setattr(job_orchestrator, "JOBS_FILE", base / "jobs.jsonl")
    monkeypatch.setattr(job_orchestrator, "PREFLIGHT_FILE", base / "preflight_results.jsonl")
    monkeypatch.setattr(job_orchestrator, "SLURM_FILE", base / "slurm_submissions.jsonl")
    monkeypatch.setattr(job_orchestrator, "PLATFORM_JOB_ARTIFACTS_DIR", jobs_base)
    monkeypatch.setattr(job_orchestrator, "DISTRIBUTED_JOBS_FILE", jobs_base / "distributed_jobs.jsonl")
    monkeypatch.setattr(job_orchestrator, "ADMISSION_REJECTIONS_FILE", jobs_base / "admission_rejections.jsonl")


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
        "replicas": 2,
        "gpu_per_replica": 1,
        "tensor_parallel": 1,
        "pipeline_parallel": 1,
        "data_parallel": 2,
        "placement_group": "pg-inference",
        "worker_group": "wg-default",
        "priority_class": "balanced",
        "oversubscribed": False,
        "oversubscription_reason_code": "fits_cluster_topology",
    }


def test_submit_job_creates_platform_artifacts(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)

    job = job_orchestrator.submit_job(_valid_payload())
    assert job["status"] == "succeeded"

    assert (tmp_path / "artifacts" / "platform" / "jobs.jsonl").exists()
    assert (tmp_path / "artifacts" / "platform" / "preflight_results.jsonl").exists()
    assert (tmp_path / "artifacts" / "platform" / "slurm_submissions.jsonl").exists()
    assert (tmp_path / "artifacts" / "platform_jobs" / "distributed_jobs.jsonl").exists()


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
    assert detail_resp.json()["topology_summary"]["replicas"] == 2
    assert detail_resp.json()["parallelism_config"]["data_parallel"] == 2


def test_preflight_fail_path(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)

    invalid = _valid_payload()
    invalid["image"] = ""
    invalid["gpu_count"] = 0

    create_resp = client.post("/platform/jobs", json=invalid)
    assert create_resp.status_code == 200
    assert create_resp.json()["status"] == "failed"


def test_quota_rejection_creates_admission_artifact(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)
    invalid = _valid_payload()
    invalid["replicas"] = 5
    invalid["gpu_per_replica"] = 2

    create_resp = client.post("/platform/jobs", json=invalid)
    assert create_resp.status_code == 200
    body = create_resp.json()
    assert body["admission_decision"] == "rejected"
    assert "quota_exceeded" in body["rejection_reason"]

    rejection_file = tmp_path / "artifacts" / "platform_jobs" / "admission_rejections.jsonl"
    assert rejection_file.exists()
    assert "quota_exceeded" in rejection_file.read_text(encoding="utf-8")


def test_invalid_parallelism_rejected(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)
    invalid = _valid_payload()
    invalid["replicas"] = 1
    invalid["gpu_per_replica"] = 2
    invalid["tensor_parallel"] = 2
    invalid["pipeline_parallel"] = 2
    invalid["data_parallel"] = 1
    invalid["oversubscription_reason_code"] = None

    create_resp = client.post("/platform/jobs", json=invalid)
    assert create_resp.status_code == 200
    body = create_resp.json()
    assert body["admission_decision"] == "rejected"
    assert "invalid_parallelism_config" in body["rejection_reason"]


def test_priority_queue_ordering(tmp_path: Path, monkeypatch) -> None:
    _set_store_paths(tmp_path, monkeypatch)
    batch = _valid_payload()
    batch["priority_class"] = "batch"
    latency = _valid_payload()
    latency["priority_class"] = "latency-sensitive"
    balanced = _valid_payload()
    balanced["priority_class"] = "balanced"

    client.post("/platform/jobs", json=batch)
    client.post("/platform/jobs", json=latency)
    client.post("/platform/jobs", json=balanced)

    list_resp = client.get("/platform/jobs")
    assert list_resp.status_code == 200
    priorities = [job["priority_class"] for job in list_resp.json()[:3]]
    assert priorities == ["latency-sensitive", "balanced", "batch"]
