# Performance Validation

This artifact documents the validation evidence expected by an inference-platform reviewer.

## Validation Targets

| Dimension | Target | Evidence |
|---|---:|---|
| API availability | `/health` returns 200 | FastAPI smoke test |
| OpenAI compatibility | `/v1/chat/completions` returns `chat.completion` | pytest schema/API tests |
| Latency | p50 and p95 recorded per run | `benchmark_results.json` |
| TTFT | Prometheus histogram and JSON artifact field | `metrics_sample.txt`, `evaluation_results.jsonl` |
| Token throughput | tokens/sec by backend | Prometheus, benchmark leaderboard |
| Streaming compatibility | OpenAI-style SSE chunks and `[DONE]` | `streaming_sse_sample.txt`, `streaming_results.jsonl` |
| Routing quality | policy and backend decisions captured | `routing_decisions.jsonl` |
| Traceability | request and backend spans emitted | `otel_traces.jsonl` |
| Load readiness | async load script produces summary JSON | `scripts/load_test.py` |

## Reviewer Notes

The local default uses deterministic mock adapters so the project can be evaluated without external keys or GPUs. Real vLLM, Triton, and OpenAI-compatible endpoints can be attached through environment variables and will preserve the same routing, metric, trace, and artifact surfaces.
