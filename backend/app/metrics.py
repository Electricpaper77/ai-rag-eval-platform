from __future__ import annotations

from prometheus_client import Counter, Histogram

TOKENS_GENERATED = Counter(
    "tokens_generated_total",
    "Total tokens generated",
    labelnames=("runtime", "model"),
)

INFERENCE_LATENCY_SECONDS = Histogram(
    "inference_latency_seconds",
    "Inference latency in seconds",
    labelnames=("runtime", "model"),
)

INFERENCE_REQUESTS_TOTAL = Counter(
    "inference_requests_total",
    "Total inference requests",
    labelnames=("model",),
)

INFERENCE_LATENCY_MS = Histogram(
    "inference_latency_ms",
    "Inference latency in milliseconds",
    labelnames=("model",),
)


def record_inference_metrics(
    runtime_label: str,
    tokens_generated: int,
    latency_ms: float,
    model_label: str | None = None,
) -> None:
    model = model_label or runtime_label
    INFERENCE_REQUESTS_TOTAL.labels(model=model).inc()
    INFERENCE_LATENCY_MS.labels(model=model).observe(max(latency_ms, 0.0))

    TOKENS_GENERATED.labels(runtime=runtime_label, model=model).inc(max(tokens_generated, 0))
    INFERENCE_LATENCY_SECONDS.labels(runtime=runtime_label, model=model).observe(max(latency_ms / 1000.0, 0.0))
