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
POSTMORTEM_FILE = PLATFORM_ARTIFACTS_DIR / "postmortem_reports.jsonl"

LIFECYCLE_ORDER = ["queued", "admitted", "running", "succeeded", "failed"]
PRIORITY_ORDER = {"latency-sensitive": 0, "balanced": 1, "batch": 2}
SUPPORTED_PRIORITY_CLASSES = set(PRIORITY_ORDER)
MAX_GPUS_PER_JOB = 8
MAX_REPLICAS_PER_JOB = 8
MAX_QUEUE_DEPTH = 32


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _legacy_platform_dir() -> Path:
    return PLATFORM_ARTIFACTS_DIR.parent / "platform"


def _ensure_store() -> None:
    PLATFORM_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    PLATFORM_JOB_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    _legacy_platform_dir().mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    _ensure_store()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def _mirror_platform_artifact(path: Path, payload: dict[str, Any]) -> None:
    legacy_path = _legacy_platform_dir() / path.name
    with legacy_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def _write_artifact(path: Path, payload: dict[str, Any], mirror_legacy: bool = False) -> None:
    _append_jsonl(path, payload)
    if mirror_legacy:
        _mirror_platform_artifact(path, payload)


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
    if topology_product > total_gpu_requested:
        reason_codes.append("invalid_parallelism_config")

    status = "admitted" if not reason_codes else "rejected"
    return status, sorted(set(reason_codes))


def submit_job(spec: dict[str, Any]) -> dict[str, Any]:
    job_id = spec.get("job_id") or f"job-{uuid4().hex[:10]}"
    submitted_at = _utc_now_iso()
    normalized_spec = _normalize_distributed_spec(spec)
    current_jobs = list_jobs()
    queue_depth = _active_queue_depth(current_jobs)
    admission_decision, admission_reasons = _validate_admission(normalized_spec, queue_depth)

    preflight = run_preflight_checks(job_id=job_id, spec=normalized_spec)
    _write_artifact(PREFLIGHT_FILE, preflight, mirror_legacy=True)

    distributed_record = {
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
    }
    _write_artifact(DISTRIBUTED_JOBS_FILE, distributed_record, mirror_legacy=True)

    record_platform_job_submitted()
    record_platform_distributed_job()
    record_platform_parallelism_config(
        tensor_parallel=normalized_spec["tensor_parallel"],
        pipeline_parallel=normalized_spec["pipeline_parallel"],
        data_parallel=normalized_spec["data_parallel"],
    )

    failed = preflight["status"] == "fail" or admission_decision == "rejected"
    if admission_reasons:
        _write_artifact(
            ADMISSION_REJECTIONS_FILE,
            {
                "job_id": job_id,
                "rejected_at": _utc_now_iso(),
                "reason_codes": admission_reasons,
                "priority_class": normalized_spec["priority_class"],
                "total_gpu_requested": normalized_spec["total_gpu_requested"],
            },
        )

    for reason in preflight.get("reason_codes", []):
        record_platform_preflight_failure(reason)
    for reason in admission_reasons:
        record_platform_preflight_failure(reason)
        record_platform_admission_rejection(reason)

    start_time = submitted_at
    end_time = _utc_now_iso()

    job = {
        "job_id": job_id,
        "workload_type": normalized_spec.get("workload_type"),
        "status": "failed" if failed else "succeeded",
        "states": ["queued", "failed"] if failed else ["queued", "admitted", "running", "succeeded"],
        "priority_class": normalized_spec["priority_class"],
        "timestamps": {
            "queued_at": submitted_at,
            "failed_at": end_time if failed else None,
            "admitted_at": None if failed else submitted_at,
            "running_at": None if failed else start_time,
            "finished_at": None if failed else end_time,
        },
        "duration_seconds": _duration_seconds(submitted_at, end_time),
        "retry_count": int(spec.get("retry_limit", spec.get("retries", 0)) or 0),
        "failure_reason": ",".join(preflight.get("reason_codes", []) + admission_reasons) if failed else None,
        "admission_decision": "rejected" if admission_reasons else ("failed_preflight" if failed else "admitted"),
        "rejection_reason": ",".join(admission_reasons) if admission_reasons else None,
        "assigned_node": None if failed else _assigned_node(normalized_spec),
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
        "gpu_count": int(normalized_spec.get("gpu_count", 0) or 0),
        "replicas": int(normalized_spec["replicas"]),
        "parallelism": {
            "tensor_parallel": normalized_spec["tensor_parallel"],
            "pipeline_parallel": normalized_spec["pipeline_parallel"],
            "data_parallel": normalized_spec["data_parallel"],
        },
        "submission_time": submitted_at,
        "start_time": None if failed else start_time,
        "end_time": end_time,
        "spec": normalized_spec,
    }

    _write_artifact(JOBS_FILE, job, mirror_legacy=True)
    _write_artifact(SLURM_FILE, _to_slurm_submission(job_id=job_id, spec=normalized_spec), mirror_legacy=True)

    if failed:
        record_platform_job_failed()
        _write_artifact(POSTMORTEM_FILE, {
            "job_id": job["job_id"],
            "failure_reason": job.get("failure_reason") or "unknown",
            "runtime_duration": float(job.get("duration_seconds", 0.0)),
            "resource_config_snapshot": {
                "gpu_count": job["spec"].get("gpu_count"),
                "cpu": job["spec"].get("cpu"),
                "memory": job["spec"].get("memory"),
                "replicas": job["spec"].get("replicas"),
            },
            "retry_count": job.get("retry_count", 0),
            "timestamp": _utc_now_iso(),
        }, mirror_legacy=True)

    record_platform_job_duration(job["duration_seconds"])
    _set_queue_metrics(list_jobs())
    return job


def list_jobs() -> list[dict[str, Any]]:
    rows = _read_jsonl(JOBS_FILE)
    rows.sort(
        key=lambda row: (
            PRIORITY_ORDER.get(row.get("priority_class", "balanced"), 999),
            row.get("submission_time", ""),
        )
    )
    _set_queue_metrics(rows)
    return rows


def get_job(job_id: str) -> dict[str, Any] | None:
    for row in list_jobs():
        if row.get("job_id") == job_id:
            return row
    return None


def _job_details(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "submission_time": job.get("submission_time"),
        "start_time": job.get("start_time"),
        "end_time": job.get("end_time"),
        "retry_count": job.get("retry_count", 0),
        "assigned_node": job.get("assigned_node"),
        "failure_reason": job.get("failure_reason"),
        "priority_class": job.get("priority_class"),
        "topology_summary": job.get("topology_summary"),
        "parallelism_config": job.get("parallelism_config"),
        "total_gpu_requested": job.get("total_gpu_requested"),
        "admission_decision": job.get("admission_decision"),
        "rejection_reason": job.get("rejection_reason"),
        "gpu_count": job.get("gpu_count"),
        "replicas": job.get("replicas"),
        "timestamps": job.get("timestamps"),
        "parallelism": job.get("parallelism"),
        "routing": job.get("routing"),
    }


def get_job_lifecycle(job_id: str) -> dict[str, Any] | None:
    row = get_job(job_id)
    if not row:
        return None
    return _job_details(row)
