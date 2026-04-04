from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from .gpu_job import GPUJobSpec
from .health_checks import simulate_job_health
from .preflight_checks import run_preflight_checks

JOBS_DIR = Path("artifacts/platform_jobs")
STATUS_FILE = JOBS_DIR / "job_status.json"


def _ensure_store() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if not STATUS_FILE.exists():
        STATUS_FILE.write_text(json.dumps({"jobs": {}}, indent=2), encoding="utf-8")


def _load_store() -> Dict[str, Any]:
    _ensure_store()
    return json.loads(STATUS_FILE.read_text(encoding="utf-8"))


def _save_store(store: Dict[str, Any]) -> None:
    _ensure_store()
    STATUS_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _resolve_lifecycle_status(status: str, submitted_at: float) -> str:
    if status in {"failed", "completed"}:
        return status

    elapsed = time.time() - submitted_at
    if elapsed >= 2:
        return "completed"
    if elapsed >= 1:
        return "running"
    return "pending"


def _hydrate_record(record: Dict[str, Any]) -> Dict[str, Any]:
    current_status = _resolve_lifecycle_status(record["status"], record["submitted_at"])
    record["status"] = current_status
    spec = GPUJobSpec(**record["spec"])
    record["health"] = simulate_job_health(spec, current_status)
    return record


def submit_job(spec: GPUJobSpec) -> Dict[str, Any]:
    preflight = run_preflight_checks(spec)
    if preflight["status"] == "fail":
        return preflight

    store = _load_store()
    now = time.time()

    record = {
        "job_id": spec.job_id,
        "status": "pending",
        "submitted_at": now,
        "updated_at": now,
        "spec": spec.to_dict(),
        "health": simulate_job_health(spec, "pending"),
    }
    store.setdefault("jobs", {})[spec.job_id] = record
    _save_store(store)

    return {
        "job_id": spec.job_id,
        "status": record["status"],
        "gpu_count": spec.gpu_count,
        "replicas": spec.replicas,
    }


def get_job_status(job_id: str) -> Dict[str, Any] | None:
    store = _load_store()
    record = store.get("jobs", {}).get(job_id)
    if not record:
        return None

    record = _hydrate_record(record)
    record["updated_at"] = time.time()
    store["jobs"][job_id] = record
    _save_store(store)

    return {
        "job_id": record["job_id"],
        "status": record["status"],
        "gpu_count": record["spec"]["gpu_count"],
        "health": record["health"],
    }


def list_jobs() -> List[Dict[str, Any]]:
    store = _load_store()
    jobs = store.get("jobs", {})
    out: List[Dict[str, Any]] = []

    for job_id, record in jobs.items():
        hydrated = _hydrate_record(record)
        hydrated["updated_at"] = time.time()
        jobs[job_id] = hydrated
        out.append(
            {
                "job_id": hydrated["job_id"],
                "status": hydrated["status"],
                "gpu_count": hydrated["spec"]["gpu_count"],
            }
        )

    _save_store(store)
    return out
