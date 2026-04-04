from __future__ import annotations

from threading import Lock

from prometheus_client import Counter, Gauge, Histogram

GPU_JOBS_SUBMITTED_TOTAL = Counter(
    "gpu_jobs_submitted_total",
    "Total number of submitted GPU orchestration jobs",
)

GPU_JOBS_COMPLETED_TOTAL = Counter(
    "gpu_jobs_completed_total",
    "Total number of completed GPU orchestration jobs",
)

GPU_JOB_DURATION_SECONDS = Histogram(
    "gpu_job_duration_seconds",
    "Duration of GPU orchestration jobs in seconds",
)

BENCHMARK_RUNS_TOTAL = Counter(
    "benchmark_runs_total",
    "Total number of distributed benchmark runs observed",
)

BENCHMARK_LATENCY_P95_MS = Gauge(
    "benchmark_latency_p95_ms",
    "P95 latency (ms) from distributed benchmark summaries",
)

BENCHMARK_TOKENS_PER_SEC = Gauge(
    "benchmark_tokens_per_sec",
    "Tokens per second from distributed benchmark summaries",
)

_completed_jobs: set[str] = set()
_seen_benchmark_runs: set[str] = set()
_state_lock = Lock()


def record_gpu_job_submitted() -> None:
    GPU_JOBS_SUBMITTED_TOTAL.inc()


def record_gpu_job_completion(job_id: str, duration_seconds: float) -> None:
    safe_duration = max(duration_seconds, 0.0)
    with _state_lock:
        if job_id in _completed_jobs:
            return
        _completed_jobs.add(job_id)
        GPU_JOBS_COMPLETED_TOTAL.inc()
        GPU_JOB_DURATION_SECONDS.observe(safe_duration)


def record_benchmark_summary(summary: dict) -> None:
    runs = summary.get("runs", []) if isinstance(summary, dict) else []
    if not runs:
        return

    latest_run = runs[-1]
    BENCHMARK_LATENCY_P95_MS.set(float(latest_run.get("p95_latency_ms", 0.0)))
    BENCHMARK_TOKENS_PER_SEC.set(float(latest_run.get("tokens_per_sec", 0.0)))

    with _state_lock:
        for run in runs:
            run_id = str(run.get("run_id", ""))
            if not run_id or run_id in _seen_benchmark_runs:
                continue
            _seen_benchmark_runs.add(run_id)
            BENCHMARK_RUNS_TOTAL.inc()
