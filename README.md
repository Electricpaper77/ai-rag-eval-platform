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

## Evaluation Dashboard

Generate the dashboard artifacts from evaluation JSONL files:

```bash
python scripts/build_eval_dashboard.py
```

Launch the API endpoints:

```bash
uvicorn dashboard.app:app --reload
```

Available endpoints:
- `GET /dashboard/summary`
- `GET /dashboard/run/{run_id}`

Example run summary JSON:

```json
{
  "run_id": "gpu_benchmark_run",
  "p50_latency_ms": 2.13,
  "p95_latency_ms": 5.5,
  "pass_rate": 0.0,
  "hallucination_rate": 0.0,
  "citation_precision": 0.0,
  "tokens_per_sec_avg": 41624.01
}
```
