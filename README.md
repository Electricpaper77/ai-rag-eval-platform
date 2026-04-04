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

## Distributed Benchmark Runner

Use `scripts/run_distributed_benchmark.py` to execute a multi-config benchmark matrix from `configs/benchmark_matrix.yaml`.

- **Multi-config benchmarking:** iterates model, batch size, and GPU count combinations and submits each run via `POST /platform/jobs`.
- **Parallel workload simulation:** models a distributed GPU benchmark workflow by tracking run IDs, waiting for completion, and recording run artifacts in `artifacts/proof/*.jsonl`.
- **Performance comparison workflow:** aggregates p95 latency and tokens/sec across all matrix runs into `artifacts/proof/distributed_benchmark_summary.json`, retrievable via `GET /platform/benchmark-summary`.

## Kubernetes GPU Batch Job

For workloads that do not need to stay online continuously, you can run GPU inference or evaluation as a Kubernetes `Job`.

- **Batch workloads:** Run one-off GPU tasks (for example, nightly benchmark runs) without keeping a long-lived deployment active.
- **Offline evaluation jobs:** Execute regression or quality evaluation jobs against saved prompts/datasets and write artifacts for later review.
- **Training-style orchestration pattern:** Use queue-and-run job patterns similar to model training pipelines, where work is scheduled, processed, and terminated automatically.

See `k8s/gpu-batch-job.yaml` for a template job manifest that runs `scripts/run_gpu_benchmark.py` with `nvidia.com/gpu: 1`.

## Automatic Model Selection

The platform now supports evaluation-driven model routing by selecting the best model run from `artifacts/proof/eval_dashboard_summary.json` using a weighted score:

- `pass_rate * 0.5`
- `- hallucination_rate * 0.3`
- `- normalized_p95_latency * 0.2`

Selection output is persisted to `artifacts/platform_jobs/best_model.json`, and can be retrieved via:

- `GET /platform/best-model`

This optimization logic simulates dynamic production routing by balancing quality signals and latency performance.
