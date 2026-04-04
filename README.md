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

## GPU Platform Orchestration Layer

This project now includes a Kubernetes-style GPU job orchestration simulation for AI inference workloads.

- **Pre-flight validation** verifies GPU jobs before submission (GPU/replica counts, image format, env shape, and resource limits).
- **Job lifecycle tracking** simulates job state transitions (`pending -> running -> completed`) with persisted metadata in `artifacts/platform_jobs/job_status.json`.
- **Platform API endpoints** expose orchestration operations:
  - `POST /platform/jobs`
  - `GET /platform/jobs`
  - `GET /platform/jobs/{job_id}`

These APIs are mounted on the existing FastAPI app and can be used to simulate internal platform workflows for GPU inference orchestration.
