from __future__ import annotations

from prometheus_client import Counter, Histogram

TOKENS_GENERATED = Counter(
    "tokens_generated_total",
    "Total tokens generated",
    labelnames=("runtime",),
)

INFERENCE_LATENCY_SECONDS = Histogram(
    "inference_latency_seconds",
    "Inference latency in seconds",
    labelnames=("runtime",),
)


def record_inference_metrics(runtime_label: str, tokens_generated: int, latency_ms: float) -> None:
    TOKENS_GENERATED.labels(runtime=runtime_label).inc(max(tokens_generated, 0))
    INFERENCE_LATENCY_SECONDS.labels(runtime=runtime_label).observe(max(latency_ms / 1000.0, 0.0))
