# AI RAG Evaluation Platform

Production-style GenAI evaluation platform for serving, regression validation, and performance benchmarking.

## Architecture Diagram

```text
Client
↓
FastAPI inference gateway
↓
runtime abstraction layer
↓
vLLM GPU inference runtime
↓
evaluation harness (JSONL artifacts)
↓
CI regression gate
↓
benchmark pipeline (tokens/sec)
↓
Kubernetes deployment (GPU)
↓
HPA autoscaling policy
```

## Proof of Work

- `artifacts/proof/regression_eval_example.jsonl`
- `artifacts/proof/load_test_summary.json`
- `artifacts/proof/benchmark_comparison.json`
- `artifacts/proof/gpu_summary.json`

## Metrics Summary

- p50 latency
- p95 latency
- tokens/sec
- eval pass rate
