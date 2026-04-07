from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .metrics import (
    record_platform_admission_rejection,
    record_platform_distributed_job,
    record_platform_job_duration,
    record_platform_job_failed,
    record_platform_parallelism_config,
    record_platform_job_submitted,
    record_platform_preflight_failure,
    set_platform_queue_depth,
    set_platform_priority_queue_depth,
)
from .preflight_checks import run_preflight_checks

PLATFORM_ARTIFACTS_DIR = Path("artifacts/platform_jobs")
JOBS_FILE = PLATFORM_ARTIFACTS_DIR / "jobs.jsonl"
PREFLIGHT_FILE = PLATFORM_ARTIFACTS_DIR / "preflight_results.jsonl"
DISTRIBUTED_FILE = PLATFORM_ARTIFACTS_DIR / "distributed_jobs.jsonl"
SLURM_FILE = PLATFORM_ARTIFACTS_DIR / "slurm_submissions.jsonl"
PLATFORM_JOB_ARTIFACTS_DIR = Path("artifacts/platform_jobs")
DISTRIBUTED_JOBS_FILE = PLATFORM_JOB_ARTIFACTS_DIR / "distributed_jobs.jsonl"
ADMISSION_REJECTIONS_FILE = PLATFORM_JOB_ARTIFACTS_DIR / "admission_rejections.jsonl"

LIFECYCLE_ORDER = ["queued", "admitted", "running", "succeeded", "failed"]
PRIORITY_ORDER = {"latency-sensitive": 0, "balanced": 1, "batch": 2}
SUPPORTED_PRIORITY_CLASSES = set(PRIORITY_ORDER)
MAX_GPUS_PER_JOB = 8
MAX_REPLICAS_PER_JOB = 8
POSTMORTEM_FILE = PLATFORM_ARTIFACTS_DIR / "postmortem_reports.jsonl"

MAX_GPUS_PER_JOB = 4
MAX_REPLICAS = 8
MAX_QUEUE_DEPTH = 32


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_store() -> None:
    PLATFORM_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    PLATFORM_JOB_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


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


def _active_queue_depth(rows: list[dict[str, Any]]) -> int:
    return len([row for row in rows if row.get("status") in {"queued", "admitted", "running"}])


def _set_queue_metrics(rows: list[dict[str, Any]]) -> None:
    set_platform_queue_depth(_active_queue_depth(rows))
    for priority_class in SUPPORTED_PRIORITY_CLASSES:
        class_depth = len(
            [
                row
                for row in rows
                if row.get("status") in {"queued", "admitted", "running"}
                and row.get("priority_class", "balanced") == priority_class
            ]
        )
        set_platform_priority_queue_depth(priority_class, class_depth)


def _normalize_distributed_spec(spec: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(spec)
    normalized.setdefault("replicas", 1)
    normalized.setdefault("gpu_per_replica", spec.get("gpu_count", 1))
    normalized.setdefault("tensor_parallel", 1)
    normalized.setdefault("pipeline_parallel", 1)
    normalized.setdefault("data_parallel", 1)
    normalized.setdefault("placement_group", "default")
    normalized.setdefault("worker_group", "default")
    normalized.setdefault("priority_class", "balanced")
    normalized.setdefault("oversubscribed", False)
    normalized.setdefault("oversubscription_reason_code", None)
    normalized["total_gpu_requested"] = int(normalized["replicas"]) * int(normalized["gpu_per_replica"])
    return normalized


def _validate_admission(spec: dict[str, Any], queue_depth: int) -> tuple[str, list[str]]:
    reason_codes: list[str] = []
    priority_class = str(spec.get("priority_class", "balanced"))
    replicas = int(spec.get("replicas", 0) or 0)
    gpu_per_replica = int(spec.get("gpu_per_replica", 0) or 0)
    tensor_parallel = int(spec.get("tensor_parallel", 0) or 0)
    pipeline_parallel = int(spec.get("pipeline_parallel", 0) or 0)
    data_parallel = int(spec.get("data_parallel", 0) or 0)
    total_gpu_requested = int(spec.get("total_gpu_requested", 0) or 0)
    topology_product = tensor_parallel * pipeline_parallel * data_parallel
    oversubscribed = bool(spec.get("oversubscribed", False))
    oversubscription_reason_code = spec.get("oversubscription_reason_code")

    if priority_class not in SUPPORTED_PRIORITY_CLASSES:
        reason_codes.append("unsupported_priority_class")
    if replicas < 1 or replicas > MAX_REPLICAS_PER_JOB:
        reason_codes.append("invalid_replica_count")
    if gpu_per_replica < 1 or total_gpu_requested <= 0:
        reason_codes.append("invalid_gpu_request")
    if total_gpu_requested > MAX_GPUS_PER_JOB:
        reason_codes.append("quota_exceeded")
    if queue_depth >= MAX_QUEUE_DEPTH:
        reason_codes.append("queue_full")
    if tensor_parallel < 1 or pipeline_parallel < 1 or data_parallel < 1:
        reason_codes.append("invalid_parallelism_config")
    if topology_product > total_gpu_requested and not (
        oversubscribed is False and oversubscription_reason_code
    ):
        reason_codes.append("invalid_parallelism_config")

    status = "admitted" if not reason_codes else "rejected"
    return status, sorted(set(reason_codes))


def submit_job(spec: dict[str, Any]) -> dict[str, Any]:
    """Submit a platform job, run pre-flight checks, and persist artifacts."""
    job_id = f"job-{uuid4().hex[:10]}"
    submitted_at = _utc_now_iso()
    normalized_spec = _normalize_distributed_spec(spec)
    queued_jobs = list_jobs()
    queue_depth = _active_queue_depth(queued_jobs)
    admission_decision, admission_reasons = _validate_admission(normalized_spec, queue_depth)
    job_id = spec.get("job_id") or f"job-{uuid4().hex[:10]}"
    submission_time = _utc_now_iso()
    all_rows = list_jobs()

    preflight = run_preflight_checks(job_id=job_id, spec=normalized_spec)
    _append_jsonl(PREFLIGHT_FILE, preflight)
    _append_jsonl(
        DISTRIBUTED_JOBS_FILE,
        {
            "job_id": job_id,
            "submitted_at": submitted_at,
            "topology": {
                "replicas": normalized_spec["replicas"],
                "gpu_per_replica": normalized_spec["gpu_per_replica"],
                "placement_group": normalized_spec["placement_group"],
                "worker_group": normalized_spec["worker_group"],
                "priority_class": normalized_spec["priority_class"],
            },
            "parallelism_config": {
                "tensor_parallel": normalized_spec["tensor_parallel"],
                "pipeline_parallel": normalized_spec["pipeline_parallel"],
                "data_parallel": normalized_spec["data_parallel"],
                "oversubscribed": normalized_spec["oversubscribed"],
                "oversubscription_reason_code": normalized_spec["oversubscription_reason_code"],
            },
            "total_gpu_requested": normalized_spec["total_gpu_requested"],
            "admission_decision": admission_decision,
            "rejection_reason": ",".join(admission_reasons) if admission_reasons else None,
        },
    )
    record_platform_job_submitted()
    record_platform_distributed_job()
    record_platform_parallelism_config(
        tensor_parallel=normalized_spec["tensor_parallel"],
        pipeline_parallel=normalized_spec["pipeline_parallel"],
        data_parallel=normalized_spec["data_parallel"],
    )

    if preflight["status"] == "fail" or admission_decision == "rejected":
        if preflight["status"] == "fail":
            record_platform_job_failed()
        for reason in preflight["reason_codes"]:
            record_platform_preflight_failure(reason)
        for reason in admission_reasons:
            record_platform_preflight_failure(reason)
            record_platform_admission_rejection(reason)
        if admission_reasons:
            _append_jsonl(
                ADMISSION_REJECTIONS_FILE,
                {
                    "job_id": job_id,
                    "rejected_at": _utc_now_iso(),
                    "reason_codes": admission_reasons,
                    "priority_class": normalized_spec["priority_class"],
                    "total_gpu_requested": normalized_spec["total_gpu_requested"],
                },
            )
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
            "workload_type": normalized_spec.get("workload_type"),
            "status": "failed",
            "states": ["queued", "failed"],
            "priority_class": normalized_spec["priority_class"],
            "timestamps": {
                "queued_at": submitted_at,
                "failed_at": _utc_now_iso(),
            },
            "duration_seconds": _duration_seconds(submitted_at, _utc_now_iso()),
            "retry_count": normalized_spec.get("retries", 0),
            "failure_reason": ",".join(preflight["reason_codes"] + admission_reasons),
            "admission_decision": "rejected" if admission_reasons else "failed_preflight",
            "rejection_reason": ",".join(admission_reasons) if admission_reasons else None,
            "assigned_node": None,
            "topology_summary": {
                "replicas": normalized_spec["replicas"],
                "gpu_per_replica": normalized_spec["gpu_per_replica"],
                "placement_group": normalized_spec["placement_group"],
                "worker_group": normalized_spec["worker_group"],
            },
            "parallelism_config": {
                "tensor_parallel": normalized_spec["tensor_parallel"],
                "pipeline_parallel": normalized_spec["pipeline_parallel"],
                "data_parallel": normalized_spec["data_parallel"],
                "oversubscribed": normalized_spec["oversubscribed"],
                "oversubscription_reason_code": normalized_spec["oversubscription_reason_code"],
            },
            "total_gpu_requested": normalized_spec["total_gpu_requested"],
            "lifecycle_metadata": {
                "admitted_node_count": 0,
                "running_replica_count": 0,
                "completed_replica_count": 0,
                "failed_replica_count": normalized_spec["replicas"],
            },
            "spec": normalized_spec,
        }
        _append_jsonl(JOBS_FILE, failed_job)
        record_platform_job_duration(failed_job["duration_seconds"])
        _set_queue_metrics(list_jobs())
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
        "workload_type": normalized_spec.get("workload_type"),
        "status": "succeeded",
        "states": ["queued", "admitted", "running", "succeeded"],
        "priority_class": normalized_spec["priority_class"],
        "timestamps": {
            "queued_at": submitted_at,
            "admitted_at": _utc_now_iso(),
            "running_at": started_at,
            "finished_at": completed_at,
        },
        "duration_seconds": _duration_seconds(started_at, completed_at),
        "retry_count": normalized_spec.get("retries", 0),
        "failure_reason": None,
        "admission_decision": "admitted",
        "rejection_reason": None,
        "assigned_node": _assigned_node(normalized_spec),
        "topology_summary": {
            "replicas": normalized_spec["replicas"],
            "gpu_per_replica": normalized_spec["gpu_per_replica"],
            "placement_group": normalized_spec["placement_group"],
            "worker_group": normalized_spec["worker_group"],
        },
        "parallelism_config": {
            "tensor_parallel": normalized_spec["tensor_parallel"],
            "pipeline_parallel": normalized_spec["pipeline_parallel"],
            "data_parallel": normalized_spec["data_parallel"],
            "oversubscribed": normalized_spec["oversubscribed"],
            "oversubscription_reason_code": normalized_spec["oversubscription_reason_code"],
        },
        "total_gpu_requested": normalized_spec["total_gpu_requested"],
        "lifecycle_metadata": {
            "admitted_node_count": 1,
            "running_replica_count": normalized_spec["replicas"],
            "completed_replica_count": normalized_spec["replicas"],
            "failed_replica_count": 0,
        },
        "spec": normalized_spec,
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
    _append_jsonl(SLURM_FILE, _to_slurm_submission(job_id=job_id, spec=normalized_spec))
    record_platform_job_duration(succeeded_job["duration_seconds"])
    _set_queue_metrics(list_jobs())

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
    rows.sort(
        key=lambda row: (
            PRIORITY_ORDER.get(row.get("priority_class", "balanced"), 999),
            row.get("timestamps", {}).get("queued_at", ""),
        )
    )
    _set_queue_metrics(rows)
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
