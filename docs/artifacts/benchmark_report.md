# Concurrency Benchmark (k6)

Target: /query endpoint on GKE LoadBalancer

Test stages:
- 10 VUs (10s)
- 25 VUs (10s)
- 50 VUs (10s)
- ramp down (10s)

Key metrics:
- p50 latency: <fill>
- p95 latency: <fill>
- error rate: <fill>
- throughput (req/s): <fill>

Notes:
- Any failure >1% is treated as a release blocker for production readiness.
