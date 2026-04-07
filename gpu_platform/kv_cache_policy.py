from __future__ import annotations

"""KV-cache-aware routing simulation for inference runtime selection."""

from typing import Any


HIGH_MEMORY_THRESHOLD_MB = 1800.0


def estimate_kv_cache_memory(tokens_in_context: int) -> float:
    """Estimate KV cache memory in MB with simple linear math."""
    safe_tokens = max(1, int(tokens_in_context))
    # Approximation: ~0.5 MB/token pair across layers/heads at inference precision.
    return round(safe_tokens * 0.5, 2)


def decide_kv_cache_runtime(tokens_in_context: int, max_batch_tokens: int = 4096) -> dict[str, Any]:
    memory_estimate_mb = estimate_kv_cache_memory(tokens_in_context)

    pressure_ratio = min(1.0, float(tokens_in_context) / max(1, max_batch_tokens))
    memory_pressure = "high" if memory_estimate_mb >= HIGH_MEMORY_THRESHOLD_MB else "normal"

    if memory_pressure == "high" or pressure_ratio >= 0.8:
        recommended_runtime = "high-memory-gpu-tier"
        batching_strategy = "small_micro_batches"
    else:
        recommended_runtime = "standard-gpu-tier"
        batching_strategy = "continuous_dynamic_batching"

    # Decode generation tends to slow as context grows.
    token_generation_cost = round(1.0 + pressure_ratio * 1.5, 3)

    return {
        "memory_estimate_mb": memory_estimate_mb,
        "memory_pressure_estimate": memory_pressure,
        "token_generation_cost": token_generation_cost,
        "recommended_runtime": recommended_runtime,
        "batching_strategy": batching_strategy,
    }
