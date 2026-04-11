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
