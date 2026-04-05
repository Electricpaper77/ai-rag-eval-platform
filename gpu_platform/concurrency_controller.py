from __future__ import annotations

"""Concurrency-aware autoscaling simulation used by /platform/summary and load tests."""

MAX_CONCURRENT_JOBS = 8
QUEUE_DELAY_PER_JOB_SECONDS = 0.75
SCALE_UP_QUEUE_THRESHOLD = 6
SCALE_DOWN_QUEUE_THRESHOLD = 1


def estimate_queue_latency(active_jobs: int, max_concurrent_jobs: int = MAX_CONCURRENT_JOBS) -> float:
    """Estimate queue wait in seconds for a given active job count."""
    safe_active = max(0, int(active_jobs))
    safe_limit = max(1, int(max_concurrent_jobs))
    queue_backlog = max(0, safe_active - safe_limit)
    return round(queue_backlog * QUEUE_DELAY_PER_JOB_SECONDS, 2)


def decide_scale_action(queue_size: int) -> str:
    """Return one of: scale_up, scale_down, or hold."""
    safe_queue = max(0, int(queue_size))
    if safe_queue >= SCALE_UP_QUEUE_THRESHOLD:
        return "scale_up"
    if safe_queue <= SCALE_DOWN_QUEUE_THRESHOLD:
        return "scale_down"
    return "hold"
