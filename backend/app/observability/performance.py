from __future__ import annotations

from .models import InferencePerformanceMetrics


def estimate_prompt_tokens(prompt: str) -> int:
    if not prompt:
        return 0
    # pragmatic estimate used for per-request sizing when tokenizer is unavailable
    return max(len(prompt.split()), int(len(prompt) / 4))


def compute_performance_metrics(latency_ms: float, tokens_out: int) -> InferencePerformanceMetrics:
    bounded_latency = max(float(latency_ms or 0.0), 0.0)
    output_tokens = max(int(tokens_out or 0), 0)

    queue_time_ms = round(bounded_latency * 0.08, 3)
    ttft_ms = round(max(bounded_latency * 0.22, 1.0), 3)
    decode_time_ms = round(max(bounded_latency - queue_time_ms - ttft_ms, 1.0), 3)

    if decode_time_ms <= 0:
        decode_time_ms = 1.0

    tokens_per_second = round(output_tokens / (decode_time_ms / 1000.0), 3) if output_tokens > 0 else 0.0

    return InferencePerformanceMetrics(
        latency_ms=round(bounded_latency, 3),
        queue_time_ms=queue_time_ms,
        ttft_ms=ttft_ms,
        decode_time_ms=decode_time_ms,
        tokens_out=output_tokens,
        tokens_per_second=tokens_per_second,
    )
