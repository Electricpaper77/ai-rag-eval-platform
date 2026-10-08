from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

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

INFERENCE_REQUEST_LATENCY_SECONDS = Histogram(
    "inference_request_latency_seconds",
    "OpenAI-compatible inference request latency in seconds",
    labelnames=("backend", "model"),
)

INFERENCE_TIME_TO_FIRST_TOKEN_SECONDS = Histogram(
    "inference_time_to_first_token_seconds",
    "OpenAI-compatible time to first token in seconds",
    labelnames=("backend", "model"),
)

INFERENCE_TOKENS_PER_SECOND = Gauge(
    "inference_tokens_per_second",
    "OpenAI-compatible generated tokens per second",
    labelnames=("backend", "model"),
)

INFERENCE_ROUTING_DECISIONS_TOTAL = Counter(
    "inference_routing_decisions_total",
    "OpenAI-compatible routing decisions",
    labelnames=("policy", "backend"),
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

EVAL_REQUESTS_TOTAL = Counter("eval_requests_total", "Total reliability evaluation requests")
EVAL_PASS_TOTAL = Counter("eval_pass_total", "Total reliability evaluations that passed")
EVAL_FAIL_TOTAL = Counter("eval_fail_total", "Total reliability evaluations that failed")
EVAL_LATENCY_SECONDS = Histogram("eval_latency_seconds", "Reliability evaluation latency in seconds")
HALLUCINATION_FAILURES_TOTAL = Counter(
    "hallucination_failures_total",
    "Total hallucination-risk evaluation failures",
)
PII_LEAKAGE_FAILURES_TOTAL = Counter(
    "pii_leakage_failures_total",
    "Total PII leakage evaluation failures",
)
PROMPT_INJECTION_FAILURES_TOTAL = Counter(
    "prompt_injection_failures_total",
    "Total prompt-injection compliance evaluation failures",
)
CITATION_FAILURES_TOTAL = Counter(
    "citation_failures_total",
    "Total citation coverage evaluation failures",
)
REFUSAL_FAILURES_TOTAL = Counter(
    "refusal_failures_total",
    "Total refusal accuracy evaluation failures",
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


def record_eval_metrics(*, passed: bool, metrics: dict[str, float], latency_seconds: float) -> None:
    EVAL_REQUESTS_TOTAL.inc()
    if passed:
        EVAL_PASS_TOTAL.inc()
    else:
        EVAL_FAIL_TOTAL.inc()
    EVAL_LATENCY_SECONDS.observe(max(latency_seconds, 0.0))

    if metrics.get("hallucination_risk", 0.0) >= 0.5:
        HALLUCINATION_FAILURES_TOTAL.inc()
    if metrics.get("pii_leakage", 0.0) > 0:
        PII_LEAKAGE_FAILURES_TOTAL.inc()
    if metrics.get("prompt_injection_compliance", 1.0) < 0.8:
        PROMPT_INJECTION_FAILURES_TOTAL.inc()
    if metrics.get("citation_coverage", 1.0) < 0.8:
        CITATION_FAILURES_TOTAL.inc()
    if metrics.get("refusal_accuracy", 1.0) < 0.8:
        REFUSAL_FAILURES_TOTAL.inc()



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
    INFERENCE_ROUTING_DECISIONS_TOTAL.labels(policy=quality_tier, backend=runtime).inc()
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


GPU_UTILIZATION_PERCENT = Gauge("gpu_utilization_percent", "GPU utilization percent", labelnames=("gpu_id", "node", "pod"))
GPU_MEMORY_USED_MB = Gauge("gpu_memory_used_mb", "GPU memory used in MiB", labelnames=("gpu_id", "node", "pod"))
GPU_MEMORY_TOTAL_MB = Gauge("gpu_memory_total_mb", "GPU memory total in MiB", labelnames=("gpu_id", "node", "pod"))
GPU_TOKENS_PER_SECOND = Gauge("tokens_per_second", "Generated tokens per second per GPU", labelnames=("gpu_id", "node", "pod"))
GPU_INFERENCE_LATENCY_P50_MS = Gauge("inference_latency_p50_ms", "P50 inference latency in milliseconds", labelnames=("gpu_id", "node", "pod"))
GPU_INFERENCE_LATENCY_P95_MS = Gauge("inference_latency_p95_ms", "P95 inference latency in milliseconds", labelnames=("gpu_id", "node", "pod"))
GPU_OBS_QUEUE_DEPTH = Gauge("queue_depth", "Pending inference queue depth per GPU-backed pod", labelnames=("gpu_id", "node", "pod"))
GPU_COLD_START_COUNT = Gauge("cold_start_count", "Observed cold starts for the GPU-backed inference pod", labelnames=("gpu_id", "node", "pod"))
GPU_COST_PER_1K_TOKENS = Gauge("cost_per_1k_tokens", "Estimated GPU serving cost per one thousand tokens", labelnames=("gpu_id", "node", "pod"))
GPU_REQUESTS_PER_GPU_HOUR = Gauge("requests_per_gpu_hour", "Estimated requests served per GPU hour", labelnames=("gpu_id", "node", "pod"))


def record_legacy_inference_metrics(backend: str, model: str, latency_ms: float, ttft_ms: float, tokens_per_second: float) -> None:
    INFERENCE_REQUEST_LATENCY_SECONDS.labels(backend=backend, model=model).observe(max(latency_ms / 1000.0, 0.0))
    INFERENCE_TIME_TO_FIRST_TOKEN_SECONDS.labels(backend=backend, model=model).observe(max(ttft_ms / 1000.0, 0.0))
    INFERENCE_TOKENS_PER_SECOND.labels(backend=backend, model=model).set(max(tokens_per_second, 0.0))


def record_gpu_status_metrics(status: dict) -> None:
    labels = {
        "gpu_id": str(status["gpu_id"]),
        "node": str(status["node"]),
        "pod": str(status["pod"]),
    }
    GPU_UTILIZATION_PERCENT.labels(**labels).set(float(status["gpu_utilization_percent"]))
    GPU_MEMORY_USED_MB.labels(**labels).set(float(status["gpu_memory_used_mb"]))
    GPU_MEMORY_TOTAL_MB.labels(**labels).set(float(status["gpu_memory_total_mb"]))
    GPU_TOKENS_PER_SECOND.labels(**labels).set(float(status["tokens_per_second"]))
    GPU_INFERENCE_LATENCY_P50_MS.labels(**labels).set(float(status["inference_latency_p50_ms"]))
    GPU_INFERENCE_LATENCY_P95_MS.labels(**labels).set(float(status["inference_latency_p95_ms"]))
    GPU_OBS_QUEUE_DEPTH.labels(**labels).set(float(status["queue_depth"]))
    GPU_COLD_START_COUNT.labels(**labels).set(float(status["cold_start_count"]))
    GPU_COST_PER_1K_TOKENS.labels(**labels).set(float(status["cost_per_1k_tokens"]))
    GPU_REQUESTS_PER_GPU_HOUR.labels(**labels).set(float(status["requests_per_gpu_hour"]))
