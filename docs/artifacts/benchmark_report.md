# Concurrency Benchmark (k6)

Target: /query endpoint on GKE LoadBalancer

Test stages:
- 10 VUs (10s)
- 25 VUs (10s)
- 50 VUs (10s)
- ramp down (10s)

Key metrics:
- p50 latency (ms): 38.452759
- p95 latency (ms): 155.4432545499999
- error rate: 1
- throughput (req/s): 396.95229137587074

Result: FAIL
Local test policy: a failure rate above 1% fails this benchmark gate. This threshold is not evidence of production readiness.
