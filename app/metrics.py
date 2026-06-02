from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


class InferenceMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests_total = Counter(
            "inference_requests_total",
            "Total inference requests",
            ["backend", "model", "status"],
            registry=self.registry,
        )
        self.request_latency = Histogram(
            "inference_request_latency_seconds",
            "Inference request latency",
            ["backend", "model"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registry,
        )
        self.tokens_generated_total = Counter(
            "inference_tokens_generated_total",
            "Total generated tokens",
            ["backend", "model"],
            registry=self.registry,
        )
        self.tokens_per_second = Gauge(
            "inference_tokens_per_second",
            "Generated tokens per second",
            ["backend", "model"],
            registry=self.registry,
        )
        self.time_to_first_token = Histogram(
            "inference_time_to_first_token_seconds",
            "Time to first generated token",
            ["backend", "model"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
            registry=self.registry,
        )
        self.time_to_first_token_latest = Gauge(
            "inference_time_to_first_token_latest_seconds",
            "Latest observed time to first generated token",
            ["backend", "model"],
            registry=self.registry,
        )
        self.prompt_tokens_total = Counter(
            "inference_prompt_tokens_total",
            "Total prompt tokens",
            ["backend", "model"],
            registry=self.registry,
        )
        self.routing_decisions_total = Counter(
            "inference_routing_decisions_total",
            "Routing decisions",
            ["policy", "backend"],
            registry=self.registry,
        )
        self.backend_errors_total = Counter(
            "inference_backend_errors_total",
            "Backend errors",
            ["backend", "error_type"],
            registry=self.registry,
        )
        self.cost_per_request = Gauge(
            "inference_cost_per_request",
            "Cost per request in USD",
            ["backend", "model"],
            registry=self.registry,
        )
        self.eval_requests_total = Counter(
            "eval_requests_total",
            "Total reliability evaluation requests",
            registry=self.registry,
        )
        self.eval_pass_total = Counter(
            "eval_pass_total",
            "Total reliability evaluations that passed",
            registry=self.registry,
        )
        self.eval_fail_total = Counter(
            "eval_fail_total",
            "Total reliability evaluations that failed",
            registry=self.registry,
        )
        self.eval_latency_seconds = Histogram(
            "eval_latency_seconds",
            "Reliability evaluation latency in seconds",
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
            registry=self.registry,
        )
        self.hallucination_failures_total = Counter(
            "hallucination_failures_total",
            "Total hallucination-risk evaluation failures",
            registry=self.registry,
        )
        self.pii_leakage_failures_total = Counter(
            "pii_leakage_failures_total",
            "Total PII leakage evaluation failures",
            registry=self.registry,
        )
        self.prompt_injection_failures_total = Counter(
            "prompt_injection_failures_total",
            "Total prompt-injection compliance evaluation failures",
            registry=self.registry,
        )
        self.citation_failures_total = Counter(
            "citation_failures_total",
            "Total citation coverage evaluation failures",
            registry=self.registry,
        )
        self.refusal_failures_total = Counter(
            "refusal_failures_total",
            "Total refusal accuracy evaluation failures",
            registry=self.registry,
        )
        gpu_labels = ["gpu_id", "node", "pod"]
        self.gpu_utilization_percent = Gauge(
            "gpu_utilization_percent",
            "GPU utilization percent for inference serving",
            gpu_labels,
            registry=self.registry,
        )
        self.gpu_memory_used_mb = Gauge(
            "gpu_memory_used_mb",
            "GPU memory used in MiB for inference serving",
            gpu_labels,
            registry=self.registry,
        )
        self.gpu_memory_total_mb = Gauge(
            "gpu_memory_total_mb",
            "Total GPU memory in MiB",
            gpu_labels,
            registry=self.registry,
        )
        self.gpu_tokens_per_second = Gauge(
            "tokens_per_second",
            "Generated tokens per second per GPU",
            gpu_labels,
            registry=self.registry,
        )
        self.inference_latency_p50_ms = Gauge(
            "inference_latency_p50_ms",
            "P50 inference latency in milliseconds",
            gpu_labels,
            registry=self.registry,
        )
        self.inference_latency_p95_ms = Gauge(
            "inference_latency_p95_ms",
            "P95 inference latency in milliseconds",
            gpu_labels,
            registry=self.registry,
        )
        self.queue_depth = Gauge(
            "queue_depth",
            "Pending inference queue depth per GPU-backed pod",
            gpu_labels,
            registry=self.registry,
        )
        self.cold_start_count = Gauge(
            "cold_start_count",
            "Observed cold starts for the GPU-backed inference pod",
            gpu_labels,
            registry=self.registry,
        )
        self.cost_per_1k_tokens_gpu = Gauge(
            "cost_per_1k_tokens",
            "Estimated GPU serving cost per one thousand tokens",
            gpu_labels,
            registry=self.registry,
        )
        self.requests_per_gpu_hour = Gauge(
            "requests_per_gpu_hour",
            "Estimated requests served per GPU hour",
            gpu_labels,
            registry=self.registry,
        )

    def record_evaluation(self, *, passed: bool, metrics: dict[str, float], latency_seconds: float) -> None:
        self.eval_requests_total.inc()
        if passed:
            self.eval_pass_total.inc()
        else:
            self.eval_fail_total.inc()
        if metrics["hallucination_risk"] >= 0.5:
            self.hallucination_failures_total.inc()
        if metrics["pii_leakage"] > 0:
            self.pii_leakage_failures_total.inc()
        if metrics["prompt_injection_compliance"] < 0.8:
            self.prompt_injection_failures_total.inc()
        if metrics["citation_coverage"] < 0.8:
            self.citation_failures_total.inc()
        if metrics["refusal_accuracy"] < 0.8:
            self.refusal_failures_total.inc()
        self.eval_latency_seconds.observe(latency_seconds)

    def record_gpu_status(self, status: dict) -> None:
        labels = {
            "gpu_id": str(status["gpu_id"]),
            "node": str(status["node"]),
            "pod": str(status["pod"]),
        }
        self.gpu_utilization_percent.labels(**labels).set(status["gpu_utilization_percent"])
        self.gpu_memory_used_mb.labels(**labels).set(status["gpu_memory_used_mb"])
        self.gpu_memory_total_mb.labels(**labels).set(status["gpu_memory_total_mb"])
        self.gpu_tokens_per_second.labels(**labels).set(status["tokens_per_second"])
        self.inference_latency_p50_ms.labels(**labels).set(status["inference_latency_p50_ms"])
        self.inference_latency_p95_ms.labels(**labels).set(status["inference_latency_p95_ms"])
        self.queue_depth.labels(**labels).set(status["queue_depth"])
        self.cold_start_count.labels(**labels).set(status["cold_start_count"])
        self.cost_per_1k_tokens_gpu.labels(**labels).set(status["cost_per_1k_tokens"])
        self.requests_per_gpu_hour.labels(**labels).set(status["requests_per_gpu_hour"])

    def render(self) -> bytes:
        return generate_latest(self.registry)
