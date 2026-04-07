from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .metrics import (
    record_platform_job_duration,
    record_platform_job_failed,
    record_platform_job_submitted,
    record_platform_preflight_failure,
    set_platform_queue_depth,
)
from .preflight_checks import run_preflight_checks

PLATFORM_ARTIFACTS_DIR = Path("artifacts/platform")
JOBS_FILE = PLATFORM_ARTIFACTS_DIR / "jobs.jsonl"
PREFLIGHT_FILE = PLATFORM_ARTIFACTS_DIR / "preflight_results.jsonl"
SLURM_FILE = PLATFORM_ARTIFACTS_DIR / "slurm_submissions.jsonl"

LIFECYCLE_ORDER = ["queued", "admitted", "running", "succeeded", "failed"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_store() -> None:
    PLATFORM_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    _ensure_store()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _duration_seconds(start_iso: str, end_iso: str) -> float:
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    return max((end - start).total_seconds(), 0.0)


def _assigned_node(job_spec: dict[str, Any]) -> str:
    selector = job_spec.get("node_selector") or {}
    gpu_pool = selector.get("gpu.pool") or selector.get("accelerator") or "shared"
    return f"gpu-node-{gpu_pool}-01"


def _to_slurm_submission(job_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "partition": "gpu",
        "gres": f"gpu:{spec['gpu_count']}",
        "cpus_per_task": spec["cpu"],
        "mem": spec["memory"],
        "container_image": spec["image"],
        "retries": spec.get("retries", 0),
        "export_env": spec.get("env", {}),
        "command": spec.get("command") or [],
    }


def submit_job(spec: dict[str, Any]) -> dict[str, Any]:
    """Submit a platform job, run pre-flight checks, and persist artifacts."""
    job_id = f"job-{uuid4().hex[:10]}"
    submitted_at = _utc_now_iso()

    preflight = run_preflight_checks(job_id=job_id, spec=spec)
    _append_jsonl(PREFLIGHT_FILE, preflight)

    if preflight["status"] == "fail":
        record_platform_job_submitted()
        record_platform_job_failed()
        for reason in preflight["reason_codes"]:
            record_platform_preflight_failure(reason)
        failed_job = {
            "job_id": job_id,
            "workload_type": spec.get("workload_type"),
            "status": "failed",
            "states": ["queued", "failed"],
            "timestamps": {
                "queued_at": submitted_at,
                "failed_at": _utc_now_iso(),
            },
            "duration_seconds": _duration_seconds(submitted_at, _utc_now_iso()),
            "retry_count": spec.get("retries", 0),
            "failure_reason": ",".join(preflight["reason_codes"]),
            "assigned_node": None,
            "spec": spec,
        }
        _append_jsonl(JOBS_FILE, failed_job)
        record_platform_job_duration(failed_job["duration_seconds"])
        set_platform_queue_depth(len([j for j in list_jobs() if j.get("status") in {"queued", "admitted", "running"}]))
        return failed_job

    started_at = _utc_now_iso()
    completed_at = _utc_now_iso()
    succeeded_job = {
        "job_id": job_id,
        "workload_type": spec.get("workload_type"),
        "status": "succeeded",
        "states": ["queued", "admitted", "running", "succeeded"],
        "timestamps": {
            "queued_at": submitted_at,
            "admitted_at": _utc_now_iso(),
            "running_at": started_at,
            "finished_at": completed_at,
        },
        "duration_seconds": _duration_seconds(started_at, completed_at),
        "retry_count": spec.get("retries", 0),
        "failure_reason": None,
        "assigned_node": _assigned_node(spec),
        "spec": spec,
    }

    _append_jsonl(JOBS_FILE, succeeded_job)
    _append_jsonl(SLURM_FILE, _to_slurm_submission(job_id=job_id, spec=spec))
    record_platform_job_submitted()
    record_platform_job_duration(succeeded_job["duration_seconds"])
    set_platform_queue_depth(len([j for j in list_jobs() if j.get("status") in {"queued", "admitted", "running"}]))
    return succeeded_job


def list_jobs() -> list[dict[str, Any]]:
    rows = _read_jsonl(JOBS_FILE)
    rows.sort(key=lambda row: row.get("timestamps", {}).get("queued_at", ""), reverse=True)
    return rows


def get_job(job_id: str) -> dict[str, Any] | None:
    for row in list_jobs():
        if row.get("job_id") == job_id:
            return row
    return None
