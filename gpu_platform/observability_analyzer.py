from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PLATFORM_JOB_ARTIFACTS_DIR = Path("artifacts/platform_jobs")
JOBS_FILE = PLATFORM_JOB_ARTIFACTS_DIR / "jobs.jsonl"
DISTRIBUTED_JOBS_FILE = PLATFORM_JOB_ARTIFACTS_DIR / "distributed_jobs.jsonl"
ADMISSION_REJECTIONS_FILE = PLATFORM_JOB_ARTIFACTS_DIR / "admission_rejections.jsonl"
ROUTING_DECISIONS_FILE = PLATFORM_JOB_ARTIFACTS_DIR / "routing_decisions.jsonl"
RUNTIME_SELECTIONS_FILE = PLATFORM_JOB_ARTIFACTS_DIR / "runtime_selections.jsonl"
FAILURE_SUMMARY_FILE = PLATFORM_JOB_ARTIFACTS_DIR / "platform_failure_summary.json"
HEALTH_REPORT_FILE = PLATFORM_JOB_ARTIFACTS_DIR / "platform_health_report.json"


LOW_QUEUE_MAX = 5
MODERATE_QUEUE_MAX = 15
IMBALANCE_THRESHOLD = 80.0


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _split_reasons(raw_reason: str | None) -> list[str]:
    if not raw_reason:
        return []
    return [reason.strip() for reason in str(raw_reason).split(",") if reason.strip()]


def collect_platform_metrics(artifacts_dir: Path = PLATFORM_JOB_ARTIFACTS_DIR) -> dict[str, Any]:
    jobs = _read_jsonl_rows(artifacts_dir / JOBS_FILE.name)
    distributed_jobs = _read_jsonl_rows(artifacts_dir / DISTRIBUTED_JOBS_FILE.name)
    admission_rejections = _read_jsonl_rows(artifacts_dir / ADMISSION_REJECTIONS_FILE.name)
    routing_decisions = _read_jsonl_rows(artifacts_dir / ROUTING_DECISIONS_FILE.name)
    runtime_selections = _read_jsonl_rows(artifacts_dir / RUNTIME_SELECTIONS_FILE.name)

    active_statuses = {"queued", "admitted", "running"}
    queue_depth = len([job for job in jobs if str(job.get("status")) in active_statuses])

    pool_counts: dict[str, int] = {}
    for decision in routing_decisions:
        pool = str(decision.get("gpu_pool", "unknown"))
        pool_counts[pool] = pool_counts.get(pool, 0) + 1

    runtime_counts: dict[str, int] = {}
    for selection in runtime_selections:
        runtime = str(selection.get("runtime") or selection.get("selected_runtime") or "unknown")
        runtime_counts[runtime] = runtime_counts.get(runtime, 0) + 1

    return {
        "platform_queue_depth": queue_depth,
        "jobs": jobs,
        "distributed_jobs": distributed_jobs,
        "admission_rejections": admission_rejections,
        "routing_decisions": routing_decisions,
        "routing_pool_counts": pool_counts,
        "runtime_selection_counts": runtime_counts,
    }


def analyze_queue_pressure(metrics: dict[str, Any]) -> dict[str, Any]:
    queue_depth = int(metrics.get("platform_queue_depth", 0) or 0)
    if queue_depth <= LOW_QUEUE_MAX:
        queue_pressure_level = "low"
    elif queue_depth <= MODERATE_QUEUE_MAX:
        queue_pressure_level = "moderate"
    else:
        queue_pressure_level = "high"

    return {
        "queue_depth": queue_depth,
        "queue_pressure_level": queue_pressure_level,
        "thresholds": {
            "low": "0-5",
            "moderate": "6-15",
            "high": "16+",
        },
    }


def analyze_runtime_selection(metrics: dict[str, Any]) -> dict[str, Any]:
    pool_counts = dict(metrics.get("routing_pool_counts", {}))
    for pool in ("latency_pool", "throughput_pool", "distributed_pool"):
        pool_counts.setdefault(pool, 0)

    total = sum(pool_counts.values())
    distribution = {
        pool: (round((count / total) * 100, 2) if total else 0.0) for pool, count in sorted(pool_counts.items())
    }

    overloaded_pools = [pool for pool, pct in distribution.items() if pct >= IMBALANCE_THRESHOLD]
    underutilized_pools = [pool for pool, pct in distribution.items() if pct == 0.0]

    imbalance_detected = bool(overloaded_pools) or (total > 0 and len(underutilized_pools) >= 2)

    runtime_usage_summary = {
        "runtime_selection_counts": dict(metrics.get("runtime_selection_counts", {})),
        "total_runtime_selections": sum(dict(metrics.get("runtime_selection_counts", {})).values()),
    }

    return {
        "routing_distribution": distribution,
        "routing_total_decisions": total,
        "imbalance_detected": imbalance_detected,
        "overloaded_pools": overloaded_pools,
        "underutilized_pools": underutilized_pools,
        "runtime_usage_summary": runtime_usage_summary,
    }


def analyze_failure_patterns(metrics: dict[str, Any]) -> dict[str, Any]:
    jobs = metrics.get("jobs", [])
    rejections = metrics.get("admission_rejections", [])

    failure_reason_frequency: dict[str, int] = {}
    retry_frequency: dict[str, int] = {}

    for job in jobs:
        for reason in _split_reasons(job.get("failure_reason")):
            failure_reason_frequency[reason] = failure_reason_frequency.get(reason, 0) + 1

        retry_bucket = str(int(job.get("retry_count", 0) or 0))
        retry_frequency[retry_bucket] = retry_frequency.get(retry_bucket, 0) + 1

    admission_rejection_reasons: dict[str, int] = {}
    for rejection in rejections:
        reason_codes = rejection.get("reason_codes", [])
        if isinstance(reason_codes, list):
            for reason in reason_codes:
                key = str(reason)
                admission_rejection_reasons[key] = admission_rejection_reasons.get(key, 0) + 1

    summary = {
        "failure_reason_frequency": dict(sorted(failure_reason_frequency.items())),
        "retry_frequency": dict(sorted(retry_frequency.items(), key=lambda item: int(item[0]))),
        "admission_rejection_reasons": dict(sorted(admission_rejection_reasons.items())),
        "total_failed_jobs": sum(failure_reason_frequency.values()),
        "total_rejections": sum(admission_rejection_reasons.values()),
    }

    FAILURE_SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    FAILURE_SUMMARY_FILE.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def analyze_parallelism_efficiency(metrics: dict[str, Any]) -> dict[str, Any]:
    distributed_jobs = metrics.get("distributed_jobs", [])
    if not distributed_jobs:
        return {
            "average_replicas": 0.0,
            "average_tensor_parallel": 0.0,
            "average_gpu_per_replica": 0.0,
            "inefficient_configurations": [],
            "total_distributed_jobs": 0,
        }

    replicas_values: list[int] = []
    tensor_parallel_values: list[int] = []
    gpu_per_replica_values: list[int] = []
    inefficient_configurations: list[dict[str, Any]] = []

    for job in distributed_jobs:
        topology = job.get("topology", {})
        parallelism = job.get("parallelism_config", {})
        replicas = int(topology.get("replicas", 1) or 1)
        tensor_parallel = int(parallelism.get("tensor_parallel", 1) or 1)
        gpu_per_replica = int(topology.get("gpu_per_replica", 1) or 1)
        total_gpu_requested = int(job.get("total_gpu_requested", replicas * gpu_per_replica) or 0)

        replicas_values.append(replicas)
        tensor_parallel_values.append(tensor_parallel)
        gpu_per_replica_values.append(gpu_per_replica)

        if total_gpu_requested >= 4 and replicas == 1 and tensor_parallel == 1:
            inefficient_configurations.append(
                {
                    "job_id": job.get("job_id"),
                    "reason": "large_workload_single_replica_single_tensor_parallel",
                    "replicas": replicas,
                    "tensor_parallel": tensor_parallel,
                    "gpu_per_replica": gpu_per_replica,
                    "total_gpu_requested": total_gpu_requested,
                }
            )

    total_jobs = len(distributed_jobs)
    return {
        "average_replicas": round(sum(replicas_values) / total_jobs, 2),
        "average_tensor_parallel": round(sum(tensor_parallel_values) / total_jobs, 2),
        "average_gpu_per_replica": round(sum(gpu_per_replica_values) / total_jobs, 2),
        "inefficient_configurations": inefficient_configurations,
        "total_distributed_jobs": total_jobs,
    }


def generate_platform_health_report(metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    metrics = metrics or collect_platform_metrics()

    queue_summary = analyze_queue_pressure(metrics)
    routing_summary = analyze_runtime_selection(metrics)
    failure_summary = analyze_failure_patterns(metrics)
    parallelism_summary = analyze_parallelism_efficiency(metrics)

    report = {
        "queue_pressure_level": queue_summary["queue_pressure_level"],
        "routing_distribution": routing_summary["routing_distribution"],
        "failure_summary": failure_summary,
        "parallelism_summary": parallelism_summary,
        "runtime_usage_summary": routing_summary["runtime_usage_summary"],
    }

    HEALTH_REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_REPORT_FILE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
