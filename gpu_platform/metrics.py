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

PLATFORM_JOBS_SUBMITTED_TOTAL = Counter(
    "platform_jobs_submitted_total",
    "Total number of platform jobs submitted",
)

PLATFORM_JOBS_FAILED_TOTAL = Counter(
    "platform_jobs_failed_total",
    "Total number of platform jobs that failed",
)

PLATFORM_JOB_DURATION_SECONDS = Histogram(
    "platform_job_duration_seconds",
    "Platform job lifecycle duration in seconds",
)

PLATFORM_PREFLIGHT_FAILURES_TOTAL = Counter(
    "platform_preflight_failures_total",
    "Total number of preflight check failures by reason code",
    labelnames=("reason_code",),
)

PLATFORM_QUEUE_DEPTH = Gauge(
    "platform_queue_depth",
    "Current number of queued/admitted/running platform jobs",
)

PLATFORM_DISTRIBUTED_JOBS_TOTAL = Counter(
    "platform_distributed_jobs_total",
    "Total number of distributed platform jobs submitted",
)

PLATFORM_ADMISSION_REJECTIONS_TOTAL = Counter(
    "platform_admission_rejections_total",
    "Total number of platform admission rejections",
    labelnames=("reason_code",),
)

PLATFORM_PRIORITY_QUEUE_DEPTH = Gauge(
    "platform_priority_queue_depth",
    "Current platform queue depth by priority class",
    labelnames=("priority_class",),
)

PLATFORM_PARALLELISM_CONFIG_TOTAL = Counter(
    "platform_parallelism_config_total",
    "Observed platform parallelism configurations",
    labelnames=("tensor_parallel", "pipeline_parallel", "data_parallel"),
)


PLATFORM_ROUTING_DECISIONS_TOTAL = Counter(
    "platform_routing_decisions_total",
    "Total number of platform routing decisions",
    labelnames=("workload_type", "priority_class", "runtime"),
)

PLATFORM_ROUTING_LATENCY_BUCKET = Histogram(
    "platform_routing_latency_bucket",
    "Latency for platform routing decision logic in milliseconds",
    labelnames=("workload_type", "gpu_pool"),
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20, 50, 100),
)

PLATFORM_KV_CACHE_STRATEGY_TOTAL = Counter(
    "platform_kv_cache_strategy_total",
    "Total number of KV cache strategy selections",
    labelnames=("strategy",),
)

PLATFORM_GPU_POOL_SELECTION_TOTAL = Counter(
    "platform_gpu_pool_selection_total",
    "Total number of GPU pool selections",
    labelnames=("gpu_pool",),
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


def record_platform_job_submitted() -> None:
    PLATFORM_JOBS_SUBMITTED_TOTAL.inc()


def record_platform_job_failed() -> None:
    PLATFORM_JOBS_FAILED_TOTAL.inc()


def record_platform_job_duration(duration_seconds: float) -> None:
    PLATFORM_JOB_DURATION_SECONDS.observe(max(duration_seconds, 0.0))


def record_platform_preflight_failure(reason_code: str) -> None:
    PLATFORM_PREFLIGHT_FAILURES_TOTAL.labels(reason_code=reason_code).inc()


def set_platform_queue_depth(depth: int) -> None:
    PLATFORM_QUEUE_DEPTH.set(max(depth, 0))


def record_platform_distributed_job() -> None:
    PLATFORM_DISTRIBUTED_JOBS_TOTAL.inc()


def record_platform_admission_rejection(reason_code: str) -> None:
    PLATFORM_ADMISSION_REJECTIONS_TOTAL.labels(reason_code=reason_code).inc()


def set_platform_priority_queue_depth(priority_class: str, depth: int) -> None:
    PLATFORM_PRIORITY_QUEUE_DEPTH.labels(priority_class=priority_class).set(max(depth, 0))


def record_platform_parallelism_config(
    tensor_parallel: int,
    pipeline_parallel: int,
    data_parallel: int,
) -> None:
    PLATFORM_PARALLELISM_CONFIG_TOTAL.labels(
        tensor_parallel=str(tensor_parallel),
        pipeline_parallel=str(pipeline_parallel),
        data_parallel=str(data_parallel),
    ).inc()


def record_routing_decision(workload_type: str, priority_class: str, runtime: str) -> None:
    PLATFORM_ROUTING_DECISIONS_TOTAL.labels(
        workload_type=workload_type,
        priority_class=priority_class,
        runtime=runtime,
    ).inc()


def record_routing_latency(workload_type: str, gpu_pool: str, latency_ms: float) -> None:
    PLATFORM_ROUTING_LATENCY_BUCKET.labels(workload_type=workload_type, gpu_pool=gpu_pool).observe(max(latency_ms, 0.0))


def record_kv_cache_strategy(strategy: str) -> None:
    PLATFORM_KV_CACHE_STRATEGY_TOTAL.labels(strategy=strategy).inc()


def record_gpu_pool_selection(gpu_pool: str) -> None:
    PLATFORM_GPU_POOL_SELECTION_TOTAL.labels(gpu_pool=gpu_pool).inc()
