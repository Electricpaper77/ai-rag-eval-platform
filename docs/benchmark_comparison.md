# Runtime Benchmark Comparison

**Static demonstration data — not a hardware benchmark.** The provider values below are fixture inputs used by comparison tests; they are not measured NVIDIA, AMD, vLLM, OpenAI, or authenticated-provider performance.

| provider | pass_rate | p50_latency_ms | p95_latency_ms | tokens_per_sec |
|---|---:|---:|---:|---:|
| openai | 0.89 | 850.0 | 1250.0 | 32.0 |
| vllm | 0.87 | 420.0 | 810.0 | 41.0 |
| mock | 0.76 | 110.0 | 180.0 | 95.0 |
