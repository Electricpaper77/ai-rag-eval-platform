from prometheus_client import Counter, Gauge, Histogram


DISTRIBUTED_REQUESTS_TOTAL = Counter(
    "distributed_requests_total",
    "Distributed inference requests by outcome",
    labelnames=("policy", "status"),
)
WORKER_REQUESTS_TOTAL = Counter(
    "distributed_worker_requests_total",
    "Requests forwarded to each distributed worker",
    labelnames=("worker_id", "status"),
)
WORKER_FAILURES_TOTAL = Counter(
    "distributed_worker_failures_total",
    "Worker health and connection failures",
    labelnames=("worker_id", "reason"),
)
ROUTING_FAILURES_TOTAL = Counter(
    "distributed_routing_failures_total",
    "Requests rejected because routing could not select a worker",
    labelnames=("reason",),
)
WORKER_HEALTH = Gauge(
    "distributed_worker_health",
    "Worker health status, one for healthy",
    labelnames=("worker_id",),
)
WORKER_ACTIVE_REQUESTS = Gauge(
    "distributed_worker_active_requests",
    "Current active requests per worker",
    labelnames=("worker_id",),
)
DISTRIBUTED_RETRIES_TOTAL = Counter(
    "distributed_retries_total",
    "Bounded retries to alternate workers",
    labelnames=("policy",),
)
DISTRIBUTED_REQUEST_LATENCY_SECONDS = Histogram(
    "distributed_request_latency_seconds",
    "Distributed inference request latency",
    labelnames=("policy", "status"),
)
