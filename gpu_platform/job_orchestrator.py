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

PLATFORM_ARTIFACTS_DIR = Path("artifacts/platform")
JOBS_FILE = PLATFORM_ARTIFACTS_DIR / "jobs.jsonl"
PREFLIGHT_FILE = PLATFORM_ARTIFACTS_DIR / "preflight_results.jsonl"
SLURM_FILE = PLATFORM_ARTIFACTS_DIR / "slurm_submissions.jsonl"
PLATFORM_JOB_ARTIFACTS_DIR = Path("artifacts/platform_jobs")
DISTRIBUTED_JOBS_FILE = PLATFORM_JOB_ARTIFACTS_DIR / "distributed_jobs.jsonl"
ADMISSION_REJECTIONS_FILE = PLATFORM_JOB_ARTIFACTS_DIR / "admission_rejections.jsonl"

LIFECYCLE_ORDER = ["queued", "admitted", "running", "succeeded", "failed"]
PRIORITY_ORDER = {"latency-sensitive": 0, "balanced": 1, "batch": 2}
SUPPORTED_PRIORITY_CLASSES = set(PRIORITY_ORDER)
MAX_GPUS_PER_JOB = 8
MAX_REPLICAS_PER_JOB = 8
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
        return failed_job

    started_at = _utc_now_iso()
    completed_at = _utc_now_iso()
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
    }

    _append_jsonl(JOBS_FILE, succeeded_job)
    _append_jsonl(SLURM_FILE, _to_slurm_submission(job_id=job_id, spec=normalized_spec))
    record_platform_job_duration(succeeded_job["duration_seconds"])
    _set_queue_metrics(list_jobs())
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
    return rows


def get_job(job_id: str) -> dict[str, Any] | None:
    for row in list_jobs():
        if row.get("job_id") == job_id:
            return row
    return None
