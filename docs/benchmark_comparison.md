# Runtime Benchmark Comparison

| provider | pass_rate | p50_latency_ms | p95_latency_ms | tokens_per_sec |
|---|---:|---:|---:|---:|
| openai | 0.89 | 850.0 | 1250.0 | 32.0 |
| vllm | 0.87 | 420.0 | 810.0 | 41.0 |
| mock | 0.76 | 110.0 | 180.0 | 95.0 |
