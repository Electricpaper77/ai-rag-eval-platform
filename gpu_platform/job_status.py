from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JOB_RUNS_PATH = Path("artifacts/platform_jobs/job_runs.jsonl")
BENCHMARK_ARTIFACT_PATHS = (
    Path("artifacts/proof/distributed_benchmark_summary.json"),
    Path("artifacts/proof/vllm_benchmark_summary.json"),
    Path("artifacts/benchmarks/gpu_real_run.json"),
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_job_run(job_id: str, model_used: str, latency_ms: float, success: bool, *, log_path: Path | None = None) -> dict[str, Any]:
    payload = {
        "job_id": job_id,
        "model_used": model_used,
        "latency_ms": round(float(latency_ms), 2),
        "success": bool(success),
        "timestamp": _utc_now_iso(),
    }

    target = log_path or JOB_RUNS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload) + "\n")

    return payload


def read_job_runs(log_path: Path | None = None) -> list[dict[str, Any]]:
    target = log_path or JOB_RUNS_PATH
    if not target.exists():
        return []

    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _last_benchmark_time() -> str | None:
    existing = [p for p in BENCHMARK_ARTIFACT_PATHS if p.exists()]
    if not existing:
        return None

    latest = max(existing, key=lambda p: p.stat().st_mtime)
    return datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat()


def platform_health_summary(log_path: Path | None = None, model_health_status: dict[str, str] | None = None) -> dict[str, Any]:
    runs = read_job_runs(log_path=log_path)
    total_jobs = len(runs)
    successes = sum(1 for row in runs if row.get("success"))
    avg_latency = (sum(float(row.get("latency_ms", 0.0)) for row in runs) / total_jobs) if total_jobs else 0.0

    return {
        "models_available": model_health_status or {"vllm": "healthy", "openai": "healthy", "mock": "healthy"},
        "last_benchmark_time": _last_benchmark_time(),
        "avg_latency_ms": round(avg_latency, 2),
        "success_rate": round((successes / total_jobs), 4) if total_jobs else 0.0,
        "total_jobs_run": total_jobs,
    }
