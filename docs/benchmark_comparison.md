# Multi-runtime benchmark comparison

| provider | pass_rate | p50_latency_ms | p95_latency_ms | tokens_per_sec |
|---|---:|---:|---:|---:|
| openai | 0.89 | 850 | 873 | 32 |
| vllm | 0.87 | 420 | 433 | 41 |
| mock | 1.00 | 50 | 51 | 20 |
