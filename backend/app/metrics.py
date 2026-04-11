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

# New portfolio-signal metrics for OpenAI-compatible local inference.
LLM_REQUESTS_TOTAL = Counter(
    "llm_requests_total",
    "Total LLM API requests",
    labelnames=("backend", "status"),
)

LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total LLM tokens returned",
    labelnames=("backend", "status"),
)

LLM_REQUEST_LATENCY_SECONDS = Histogram(
    "llm_request_latency_seconds",
    "LLM request latency in seconds",
    labelnames=("backend", "status"),
)

GRAPHRAG_REQUESTS_TOTAL = Counter(
    "graphrag_requests_total",
    "Total GraphRAG evaluation requests",
)

GRAPHRAG_LATENCY_SECONDS = Histogram(
    "graphrag_latency_seconds",
    "GraphRAG evaluation latency in seconds",
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


def record_llm_api_metrics(backend: str, status: str, total_tokens: int, latency_ms: float) -> None:
    LLM_REQUESTS_TOTAL.labels(backend=backend, status=status).inc()
    LLM_TOKENS_TOTAL.labels(backend=backend, status=status).inc(max(total_tokens, 0))
    LLM_REQUEST_LATENCY_SECONDS.labels(backend=backend, status=status).observe(max(latency_ms / 1000.0, 0.0))



INFERENCE_PIPELINE_EVENTS_TOTAL = Counter(
    "inference_pipeline_events_total",
    "Inference pipeline events by status",
    labelnames=("runtime", "model", "status"),
)

INFERENCE_QUEUE_TIME_MS = Histogram(
    "inference_queue_time_ms",
    "Estimated queue time in milliseconds",
    labelnames=("runtime", "model"),
)

INFERENCE_TTFT_MS = Histogram(
    "inference_ttft_ms",
    "Time to first token in milliseconds",
    labelnames=("runtime", "model"),
)

INFERENCE_DECODE_TIME_MS = Histogram(
    "inference_decode_time_ms",
    "Decode phase time in milliseconds",
    labelnames=("runtime", "model"),
)

INFERENCE_DECODE_THROUGHPUT_TPS = Histogram(
    "inference_decode_throughput_tps",
    "Decode throughput in tokens per second",
    labelnames=("runtime", "model"),
)


def record_inference_observability_metrics(
    runtime: str,
    model: str,
    status: str,
    queue_time_ms: float,
    ttft_ms: float,
    decode_time_ms: float,
    tokens_per_second: float,
) -> None:
    INFERENCE_PIPELINE_EVENTS_TOTAL.labels(runtime=runtime, model=model, status=status).inc()
    INFERENCE_QUEUE_TIME_MS.labels(runtime=runtime, model=model).observe(max(queue_time_ms, 0.0))
    INFERENCE_TTFT_MS.labels(runtime=runtime, model=model).observe(max(ttft_ms, 0.0))
    INFERENCE_DECODE_TIME_MS.labels(runtime=runtime, model=model).observe(max(decode_time_ms, 0.0))
    INFERENCE_DECODE_THROUGHPUT_TPS.labels(runtime=runtime, model=model).observe(max(tokens_per_second, 0.0))


from prometheus_client import Gauge

ROUTER_DECISIONS_TOTAL = Counter(
    "router_decisions_total",
    "Total routing decisions",
    labelnames=("runtime", "quality_tier"),
)

GPU_QUEUE_DEPTH = Gauge(
    "gpu_queue_depth",
    "Current GPU runtime queue depth",
    labelnames=("runtime",),
)


def record_router_metrics(runtime: str, quality_tier: str, queue_depth: int) -> None:
    ROUTER_DECISIONS_TOTAL.labels(runtime=runtime, quality_tier=quality_tier).inc()
    GPU_QUEUE_DEPTH.labels(runtime=runtime).set(max(queue_depth, 0))


RELIABILITY_REQUESTS_TOTAL = Counter(
    "reliability_requests_total",
    "Reliability request outcomes",
    labelnames=("status",),
)

RELIABILITY_RETRY_TOTAL = Counter(
    "reliability_retry_total",
    "Total retries observed",
)

RELIABILITY_TIMEOUT_TOTAL = Counter(
    "reliability_timeout_total",
    "Total timeouts observed",
)

RELIABILITY_ERROR_RATE = Gauge(
    "reliability_error_rate",
    "Current observed error rate",
)

RELIABILITY_SUCCESS_RATE = Gauge(
    "reliability_success_rate",
    "Current observed success rate",
)

DISTRIBUTED_RUNTIME_QUEUE_DEPTH = Gauge(
    "distributed_runtime_queue_depth",
    "Simulated distributed benchmark queue depth",
    labelnames=("runtime",),
)

DISTRIBUTED_RUNTIME_LATENCY_MS = Histogram(
    "distributed_runtime_latency_ms",
    "Simulated distributed benchmark latency in milliseconds",
    labelnames=("runtime",),
)


def record_reliability_metrics(
    *,
    status: str,
    retries: int,
    timed_out: bool,
    total_requests: int,
    error_count: int,
    success_count: int,
) -> None:
    RELIABILITY_REQUESTS_TOTAL.labels(status=status).inc()
    RELIABILITY_RETRY_TOTAL.inc(max(retries, 0))
    if timed_out:
        RELIABILITY_TIMEOUT_TOTAL.inc()

    if total_requests > 0:
        RELIABILITY_ERROR_RATE.set(max(error_count, 0) / total_requests)
        RELIABILITY_SUCCESS_RATE.set(max(success_count, 0) / total_requests)


def record_distributed_runtime_metrics(runtime: str, queue_depth: int, latency_ms: float) -> None:
    DISTRIBUTED_RUNTIME_QUEUE_DEPTH.labels(runtime=runtime).set(max(queue_depth, 0))
    DISTRIBUTED_RUNTIME_LATENCY_MS.labels(runtime=runtime).observe(max(latency_ms, 0.0))
