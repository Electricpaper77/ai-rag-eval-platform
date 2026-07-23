from __future__ import annotations

import math
from typing import Iterable


def percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return None
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def summarize(records: list[dict]) -> dict:
    measured = [r for r in records if r.get("success") and not r.get("warmup") and not r.get("cache_hit")]
    completed = [r for r in records if r.get("completed")]
    successes = [r for r in completed if r.get("success")]
    wall = sum(float(r.get("latency_seconds") or 0) for r in measured)
    token_records = [r for r in measured if r.get("output_tokens") is not None]
    output_tokens = sum(int(r.get("output_tokens") or 0) for r in token_records)
    total = len(records)
    duration = max((float(r.get("ended_monotonic") or 0) for r in records), default=0) - min((float(r.get("started_monotonic") or 0) for r in records), default=0)
    return {
        "total_requested": total,
        "completed_requests": len(completed), "successful_requests": len(successes),
        "failed_requests": len(completed) - len(successes),
        "success_rate": len(successes) / len(completed) if completed else None,
        "latency_p50_seconds": percentile([r.get("latency_seconds") for r in measured if r.get("latency_seconds") is not None], .5),
        "latency_p95_seconds": percentile([r.get("latency_seconds") for r in measured if r.get("latency_seconds") is not None], .95),
        "max_latency_seconds": max((r.get("latency_seconds") for r in measured if r.get("latency_seconds") is not None), default=None),
        "ttft_p50_seconds": percentile([r.get("ttft_seconds") for r in measured if r.get("ttft_seconds") is not None], .5),
        "ttft_p95_seconds": percentile([r.get("ttft_seconds") for r in measured if r.get("ttft_seconds") is not None], .95),
        "output_tokens_per_second": output_tokens / wall if wall and token_records else None,
        "aggregate_output_tokens_per_second": output_tokens / duration if duration > 0 and token_records else None,
        "requests_per_second": len(measured) / duration if duration > 0 else None,
        "cache_hits": sum(bool(r.get("cache_hit")) for r in records),
        "retry_count": sum(int(r.get("retries") or 0) for r in records),
    }
