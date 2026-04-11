from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import Counter, Gauge, Histogram

GPU_PLATFORM_REQUESTS_TOTAL = Counter(
    "gpu_platform_requests_total",
    "GPU platform routed requests",
    labelnames=("backend", "decision", "quality_tier"),
)
GPU_PLATFORM_LATENCY_MS = Histogram(
    "gpu_platform_latency_ms",
    "Observed end-to-end latency in milliseconds",
    labelnames=("backend",),
)
GPU_PLATFORM_TOKENS_PER_SEC = Histogram(
    "gpu_platform_tokens_per_second",
    "Observed generation throughput (tokens/sec)",
    labelnames=("backend",),
)
GPU_PLATFORM_QUEUE_DEPTH = Gauge(
    "gpu_platform_queue_depth",
    "Current estimated queue depth by backend",
    labelnames=("backend",),
)
GPU_PLATFORM_ADMISSION_DENIALS_TOTAL = Counter(
    "gpu_platform_admission_denials_total",
    "Admission denials due to capacity constraints",
    labelnames=("backend", "reason"),
)
GPU_PLATFORM_AUTOSCALE_RECOMMENDATIONS_TOTAL = Counter(
    "gpu_platform_autoscale_recommendations_total",
    "Autoscaling recommendations emitted by the control plane",
    labelnames=("backend", "recommendation"),
)


@dataclass
class RoutingMetricEvent:
    backend: str
    quality_tier: str
    decision: str
    latency_ms: float
    tokens_per_second: float
    queue_depth: int


def record_routing_metrics(event: RoutingMetricEvent) -> None:
    GPU_PLATFORM_REQUESTS_TOTAL.labels(
        backend=event.backend,
        decision=event.decision,
        quality_tier=event.quality_tier,
    ).inc()
    GPU_PLATFORM_LATENCY_MS.labels(backend=event.backend).observe(max(event.latency_ms, 0.0))
    GPU_PLATFORM_TOKENS_PER_SEC.labels(backend=event.backend).observe(max(event.tokens_per_second, 0.0))
    GPU_PLATFORM_QUEUE_DEPTH.labels(backend=event.backend).set(max(event.queue_depth, 0))


def record_admission_denial(backend: str, reason: str) -> None:
    GPU_PLATFORM_ADMISSION_DENIALS_TOTAL.labels(backend=backend, reason=reason).inc()


def record_autoscale_recommendation(backend: str, recommendation: str) -> None:
    GPU_PLATFORM_AUTOSCALE_RECOMMENDATIONS_TOTAL.labels(
        backend=backend,
        recommendation=recommendation,
    ).inc()
