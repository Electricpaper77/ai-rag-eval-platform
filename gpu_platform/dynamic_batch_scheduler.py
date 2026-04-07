from __future__ import annotations

"""Dynamic batching simulation utilities for GPU inference scheduling."""

from statistics import mean
from typing import Any


def _bucket_for_tokens(token_length: int) -> str:
    if token_length <= 128:
        return "short"
    if token_length <= 512:
        return "medium"
    return "long"


def _estimate_service_time_ms(token_length: int) -> float:
    # Simple approximation: longer prompts cost more prefill + decode time.
    return 15.0 + token_length * 0.55


def schedule_requests(
    request_queue: list[dict[str, Any]],
    batch_window_ms: int = 15,
    max_batch_size: int = 8,
    latency_sla_ms: int = 1200,
) -> dict[str, Any]:
    """Group requests into batch groups while respecting latency budgets.

    Expected request schema:
      {
        "request_id": "req-001",
        "token_length": 256,
        "arrival_ms": 0,
        "latency_budget_ms": 1000,  # optional, defaults to latency_sla_ms
      }
    """

    if not request_queue:
        return {
            "batch_groups": [],
            "expected_latency": 0.0,
            "gpu_utilization_estimate": 0.0,
        }

    queue = sorted(request_queue, key=lambda r: float(r.get("arrival_ms", 0.0)))
    buckets: dict[str, list[dict[str, Any]]] = {"short": [], "medium": [], "long": []}
    batch_groups: list[dict[str, Any]] = []
    finalized_batches = 0
    total_capacity = 0

    def flush_bucket(bucket_name: str, now_ms: float) -> None:
        nonlocal finalized_batches, total_capacity
        pending = buckets[bucket_name]
        while pending:
            chunk = pending[:max_batch_size]
            del pending[:max_batch_size]

            service_time = max(_estimate_service_time_ms(int(r["token_length"])) for r in chunk)
            avg_wait = mean(max(0.0, now_ms - float(r.get("arrival_ms", now_ms))) for r in chunk)
            expected_latency = round(avg_wait + service_time, 2)

            batch_groups.append(
                {
                    "token_bucket": bucket_name,
                    "request_ids": [str(r.get("request_id", "unknown")) for r in chunk],
                    "batch_size": len(chunk),
                    "avg_token_length": round(mean(int(r["token_length"]) for r in chunk), 2),
                    "expected_batch_latency_ms": expected_latency,
                }
            )
            finalized_batches += 1
            total_capacity += max_batch_size

    for request in queue:
        tokens = int(request.get("token_length", 128))
        bucket_name = _bucket_for_tokens(tokens)
        arrival_ms = float(request.get("arrival_ms", 0.0))
        budget = float(request.get("latency_budget_ms", latency_sla_ms))

        buckets[bucket_name].append(
            {
                "request_id": request.get("request_id", f"req-{len(batch_groups)+1}"),
                "token_length": tokens,
                "arrival_ms": arrival_ms,
                "latency_budget_ms": budget,
            }
        )

        # Flush immediately if batch is full to maximize throughput.
        if len(buckets[bucket_name]) >= max_batch_size:
            flush_bucket(bucket_name, now_ms=arrival_ms + batch_window_ms)
            continue

        # Head-of-line blocking guard: flush bucket if oldest request would breach budget.
        oldest = buckets[bucket_name][0]
        waited_ms = max(0.0, arrival_ms - float(oldest.get("arrival_ms", arrival_ms)))
        predicted_latency = waited_ms + _estimate_service_time_ms(int(oldest["token_length"]))
        if predicted_latency + batch_window_ms > min(float(oldest["latency_budget_ms"]), float(latency_sla_ms)):
            flush_bucket(bucket_name, now_ms=arrival_ms)

    last_arrival = float(queue[-1].get("arrival_ms", 0.0))
    for bucket_name in ("short", "medium", "long"):
        if buckets[bucket_name]:
            flush_bucket(bucket_name, now_ms=last_arrival + batch_window_ms)

    avg_latency = round(mean(g["expected_batch_latency_ms"] for g in batch_groups), 2)
    utilization = 0.0 if total_capacity == 0 else round(sum(g["batch_size"] for g in batch_groups) / total_capacity, 3)

    return {
        "batch_groups": batch_groups,
        "expected_latency": avg_latency,
        "gpu_utilization_estimate": utilization,
        "scheduler_config": {
            "batch_window_ms": batch_window_ms,
            "max_batch_size": max_batch_size,
            "latency_sla_ms": latency_sla_ms,
            "num_batches": finalized_batches,
        },
    }
