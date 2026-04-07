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

PLATFORM_ARTIFACTS_DIR = Path("artifacts/platform_jobs")
JOBS_FILE = PLATFORM_ARTIFACTS_DIR / "jobs.jsonl"
PREFLIGHT_FILE = PLATFORM_ARTIFACTS_DIR / "preflight_results.jsonl"
DISTRIBUTED_FILE = PLATFORM_ARTIFACTS_DIR / "distributed_jobs.jsonl"
SLURM_FILE = PLATFORM_ARTIFACTS_DIR / "slurm_submissions.jsonl"
POSTMORTEM_FILE = PLATFORM_ARTIFACTS_DIR / "postmortem_reports.jsonl"

MAX_GPUS_PER_JOB = 4
MAX_REPLICAS = 8
MAX_QUEUE_DEPTH = 32


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
        if line:
            rows.append(json.loads(line))
    return rows


def _duration_seconds(start_iso: str, end_iso: str) -> float:
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    return max((end - start).total_seconds(), 0.0)


def _active_queue_depth(rows: list[dict[str, Any]]) -> int:
    return len([row for row in rows if row.get("status") in {"queued", "admitted", "running"}])


def _assigned_node(spec: dict[str, Any]) -> str:
    selector = spec.get("node_selector") or {}
    role = selector.get("accelerator") or selector.get("gpu.pool") or "general"
    return f"gpu-{role}-node-01"


def _to_slurm_submission(job_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "partition": spec.get("queue", "gpu"),
        "gpus": int(spec.get("gpu_count", 1) or 1),
        "cpus": str(spec.get("cpu", "4")),
        "memory": str(spec.get("memory", "16Gi")),
        "time_limit": int(spec.get("timeout_seconds", 3600) or 3600),
    }


def _admission_reason(spec: dict[str, Any], existing_rows: list[dict[str, Any]]) -> str | None:
    if int(spec.get("gpu_count", 0) or 0) > MAX_GPUS_PER_JOB:
        return "quota_exceeded"
    if int(spec.get("replicas", 1) or 1) > MAX_REPLICAS:
        return "max_replicas_exceeded"
    if _active_queue_depth(existing_rows) >= MAX_QUEUE_DEPTH:
        return "queue_depth_exceeded"
    return None


def _postmortem_report(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "failure_reason": job.get("failure_reason") or "unknown",
        "runtime_duration": float(job.get("runtime_duration", 0.0)),
        "resource_config_snapshot": {
            "gpu_count": job["spec"].get("gpu_count"),
            "cpu": job["spec"].get("cpu"),
            "memory": job["spec"].get("memory"),
            "replicas": job["spec"].get("replicas"),
        },
        "retry_count": job.get("retry_count", 0),
        "timestamp": _utc_now_iso(),
    }


def _job_details(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "submission_time": job["submission_time"],
        "start_time": job.get("start_time"),
        "end_time": job.get("end_time"),
        "retry_count": job.get("retry_count", 0),
        "assigned_node": job.get("assigned_node"),
        "failure_reason": job.get("failure_reason"),
    }


def submit_job(spec: dict[str, Any]) -> dict[str, Any]:
    job_id = spec.get("job_id") or f"job-{uuid4().hex[:10]}"
    submission_time = _utc_now_iso()
    all_rows = list_jobs()

    preflight = run_preflight_checks(job_id=job_id, spec=spec)
    _append_jsonl(PREFLIGHT_FILE, preflight)

    admission_failure = _admission_reason(spec, all_rows)
    if admission_failure:
        preflight["status"] = "fail"
        preflight["reason_codes"] = sorted(set(preflight["reason_codes"] + [admission_failure]))
        _append_jsonl(PREFLIGHT_FILE, {"job_id": job_id, "status": "fail", "reason_codes": [admission_failure]})

    if preflight["status"] == "fail":
        failure_reason = ",".join(preflight["reason_codes"])
        failed_at = _utc_now_iso()
        failed_job = {
            "job_id": job_id,
            "workload_type": spec.get("workload_type"),
            "status": "failed",
            "submission_time": submission_time,
            "start_time": None,
            "end_time": failed_at,
            "retry_count": int(spec.get("retry_limit", spec.get("retries", 0)) or 0),
            "assigned_node": None,
            "failure_reason": failure_reason,
            "runtime_duration": _duration_seconds(submission_time, failed_at),
            "spec": spec,
        }
        _append_jsonl(JOBS_FILE, failed_job)
        _append_jsonl(POSTMORTEM_FILE, _postmortem_report(failed_job))

        record_platform_job_submitted()
        record_platform_job_failed()
        for reason in preflight["reason_codes"]:
            record_platform_preflight_failure(reason)
        record_platform_job_duration(failed_job["runtime_duration"])
        set_platform_queue_depth(_active_queue_depth(list_jobs()))
        return failed_job

    start_time = _utc_now_iso()
    end_time = _utc_now_iso()
    succeeded_job = {
        "job_id": job_id,
        "workload_type": spec.get("workload_type"),
        "status": "succeeded",
        "submission_time": submission_time,
        "start_time": start_time,
        "end_time": end_time,
        "retry_count": int(spec.get("retry_limit", spec.get("retries", 0)) or 0),
        "assigned_node": _assigned_node(spec),
        "failure_reason": None,
        "runtime_duration": _duration_seconds(start_time, end_time),
        "spec": spec,
    }
    _append_jsonl(JOBS_FILE, succeeded_job)

    distributed_meta = {
        "job_id": job_id,
        "workload_type": spec.get("workload_type"),
        "replicas": int(spec.get("replicas", 1) or 1),
        "tensor_parallel": int(spec.get("tensor_parallel", 1) or 1),
        "pipeline_parallel": int(spec.get("pipeline_parallel", 1) or 1),
        "gpu_per_replica": int(spec.get("gpu_per_replica", 1) or 1),
    }
    _append_jsonl(DISTRIBUTED_FILE, distributed_meta)
    _append_jsonl(SLURM_FILE, _to_slurm_submission(job_id=job_id, spec=spec))

    record_platform_job_submitted()
    record_platform_job_duration(succeeded_job["runtime_duration"])
    set_platform_queue_depth(_active_queue_depth(list_jobs()))
    return succeeded_job


def list_jobs() -> list[dict[str, Any]]:
    rows = _read_jsonl(JOBS_FILE)
    rows.sort(key=lambda row: row.get("submission_time", ""), reverse=True)
    return rows


def get_job(job_id: str) -> dict[str, Any] | None:
    for row in list_jobs():
        if row.get("job_id") == job_id:
            return row
    return None


def get_job_lifecycle(job_id: str) -> dict[str, Any] | None:
    row = get_job(job_id)
    if not row:
        return None
    return _job_details(row)
