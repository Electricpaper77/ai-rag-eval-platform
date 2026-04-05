from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JOB_RUNS_DIR = Path("artifacts/job_runs")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_store() -> None:
    JOB_RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _job_sequence() -> int:
    _ensure_store()
    max_id = 0
    for path in JOB_RUNS_DIR.glob("job_*.json"):
        try:
            max_id = max(max_id, int(path.stem.split("_")[1]))
        except (IndexError, ValueError):
            continue
    return max_id + 1


def _job_file(job_id: str) -> Path:
    _ensure_store()
    return JOB_RUNS_DIR / f"{job_id}.json"


def _read_job(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_job(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def submit_job(
    model: str,
    dataset: str,
    runtime: str,
    gpu_required: bool = True,
) -> str:
    """Create a simulated platform job and persist a structured job artifact."""
    job_id = f"job_{_job_sequence():03d}"
    submitted_at = _utc_now_iso()
    completed_at = _utc_now_iso()

    job_payload = {
        "job_id": job_id,
        "status": "completed",
        "submitted_at": submitted_at,
        "completed_at": completed_at,
        "dataset": dataset,
        "runtime": runtime,
        "avg_latency": 142.5,
        "success_rate": 0.99,
        "model": model,
        "gpu_required": gpu_required,
        "runtime_used": runtime,
        "dataset_used": dataset,
        "start_time": submitted_at,
        "end_time": completed_at,
        "latency_summary": {
            "p50_ms": 120.0,
            "p95_ms": 215.0,
            "avg_ms": 142.5,
        },
    }

    _write_job(_job_file(job_id), job_payload)
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    path = _job_file(job_id)
    if not path.exists():
        return None
    return _read_job(path)


def list_jobs() -> list[dict[str, Any]]:
    _ensure_store()
    jobs: list[dict[str, Any]] = []
    for path in sorted(JOB_RUNS_DIR.glob("job_*.json")):
        jobs.append(_read_job(path))
    return jobs
