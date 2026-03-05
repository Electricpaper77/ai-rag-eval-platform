## Observability Proof

- Endpoint: `/metrics` (Prometheus format)
- Service: `ai-rag-eval` (Cloud Run)
- Metrics exported:
  - `http_requests_total` (path/method/status)
  - `http_request_latency_seconds` (histogram)
- Proof file: `docs/artifacts/metrics_sample.txt`
