# AI RAG Evaluation Platform

Production-style GenAI evaluation platform for serving, regression validation, and performance benchmarking.

## Architecture Overview

```mermaid
flowchart TD

A[Client / Evaluation Requests] --> B[FastAPI API Layer]

B --> C[Runtime Router]

C --> D[LLM Evaluation Harness]
D --> E[JSONL Artifacts]

B --> F[GPU Job Orchestration Layer]

F --> G[Distributed Benchmark Runner]

G --> H[Prometheus Metrics]

F --> I[Kubernetes GPU Job Template]

I --> J[Helm Chart Packaging]

I --> K[Terraform IaC Scaffold]

G --> L[Model Selection Logic]

H --> M[/metrics endpoint]

E --> N[Regression Gating Signals]
```

## What This Project Demonstrates

| Capability | Proof artifact | Hiring signal |
| --- | --- | --- |
| LLM regression gating | `artifacts/proof/regression_eval_example.jsonl` | Can enforce quality gates before release. |
| RAG reliability / guardrails | `artifacts/proof/eval_dashboard_summary.json` | Tracks hallucination/pass-rate behavior with measurable outputs. |
| GPU workload orchestration | `k8s/gpu-batch-job.yaml` + platform job APIs | Understands GPU job lifecycle and pre-flight controls. |
| Distributed benchmarking | `artifacts/proof/distributed_benchmark_summary.json` | Can run multi-config performance comparisons and summarize results. |
| Prometheus observability | `GET /metrics` plus benchmark/job metric families | Exposes platform and workload telemetry for SRE workflows. |
| Infrastructure as Code | `infra/terraform/main.tf` + `helm/gpu-inference/` | Comfortable with reproducible environment provisioning. |
| Kubernetes networking isolation | `k8s/network-policy.yaml` | Applies least-privilege service boundaries for GPU APIs. |
| Distributed training awareness | `configs/distributed_training.yaml` | Understands DDP launch shape and cluster coordination basics. |

## Proof Artifacts

- `artifacts/proof/regression_eval_example.jsonl`
- `artifacts/proof/eval_dashboard_summary.json`
- `artifacts/proof/distributed_benchmark_summary.json`
- `artifacts/platform_jobs/best_model.json`
- `k8s/gpu-batch-job.yaml`
- `k8s/network-policy.yaml`
- `infra/terraform/main.tf`
- `helm/gpu-inference/`
- `configs/vllm_gpu_config.yaml`
- `configs/distributed_training.yaml`

## Example Metrics Snapshot

```json
{
  "p50_latency_ms": 2.13,
  "p95_latency_ms": 5.5,
  "pass_rate": 0.92,
  "hallucination_rate": 0.04,
  "tokens_per_sec_avg": 41624.01
}
```

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



## vLLM GPU Benchmark

Use `scripts/run_vllm_benchmark.py` with `configs/vllm_gpu_config.yaml` to simulate GPU inference behavior and emit `artifacts/proof/vllm_benchmark_summary.json`.

- **Continuous batching simulation:** benchmarks a prompt batch and captures per-request prefill/decode/request latency.
- **Throughput optimization signal:** computes request-level and aggregate `tokens_per_sec` to model serving efficiency.
- **Latency distribution measurement:** tracks p95 plus average latency metrics for realistic inference SLO monitoring.

The summary can be retrieved from the platform API via `GET /platform/vllm-benchmark`.

## Platform Observability

The GPU orchestration and distributed benchmark simulation now exports Prometheus metrics via the existing `GET /metrics` endpoint.

- **Job-level metrics:**
  - `gpu_jobs_submitted_total`
  - `gpu_jobs_completed_total`
  - `gpu_job_duration_seconds`
- **Benchmark performance tracking:**
  - `benchmark_runs_total`
  - `benchmark_latency_p95_ms`
  - `benchmark_tokens_per_sec`
- **Prometheus integration:**
  - `POST /platform/jobs` increments submission counters.
  - Job completion tracking records completion counters and job-duration histogram observations.
  - `GET /platform/benchmark-summary` updates benchmark run counters and p95/tokens gauges from distributed summary artifacts.

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

## Helm Deployment Option

For production-style packaging and templating of GPU inference services, use the Helm chart in `helm/gpu-inference`.

Render manifests locally:

```bash
helm template helm/gpu-inference
```

This chart deploys `vllm/vllm-openai:latest` with `MODEL_NAME=mistralai/Mistral-7B-Instruct-v0.2` and requests one GPU via `nvidia.com/gpu: 1`.

## Network Isolation Model

Use `k8s/network-policy.yaml` to enforce default-deny ingress behavior for GPU inference pods while still permitting trusted platform traffic.

- **Default deny for external ingress:** The policy applies to pods labeled `app.kubernetes.io/name: gpu-inference-service` and only defines explicit allow rules, which blocks all other inbound traffic by default.
- **Allowed internal namespace:** Ingress is allowed only from the Kubernetes namespace `internal-platform`.
- **Restricted ports:** Only TCP `8000` (inference API) and TCP `9090` (metrics/sidecar style traffic) are opened.

Apply with:

```bash
kubectl apply -f k8s/network-policy.yaml
```

## Distributed Training Pattern

Use `configs/distributed_training.yaml` as a starter skeleton for multi-node PyTorch training.

```yaml
backend: nccl
num_nodes: 2
gpus_per_node: 1
```

Launch example:

```bash
torchrun \
  --nnodes=2 \
  --nproc_per_node=1 \
  train.py
```

## AMD / AI Platform Relevance

| Infrastructure signal | Evidence in this repository | AMD / AI platform relevance |
| --- | --- | --- |
| GPU pre-flight validation | GPU job API validation flow before workload submission | Mirrors production-grade guardrails for accelerator scheduling and admission control. |
| Job lifecycle orchestration | Persisted `pending -> running -> completed` transitions in platform job artifacts | Reflects cluster job state management expected in enterprise AI platforms. |
| Internal platform APIs | Scheduling, job status, benchmark, and summary endpoints | Demonstrates service-oriented interfaces for multi-tenant AI infrastructure operations. |
| Kubernetes-ready GPU packaging | Deployment, batch job, and network policy manifests plus Helm packaging | Aligns with containerized GPU deployment patterns used in modern AI environments. |
| Observability and SRE signals | Prometheus metrics via `/metrics` for jobs and benchmark performance | Supports reliability, capacity planning, and performance governance for AI systems. |

## vLLM Runtime Example

Use the sample GPU runtime config in `configs/vllm_gpu_config.yaml`:

```yaml
model: mistralai/Mistral-7B-Instruct-v0.2

tensor_parallel_size: 1

max_model_len: 4096

gpu_memory_utilization: 0.85
```

Serve command:

```bash
python -m vllm.entrypoints.openai.api_server \\
  --model mistralai/Mistral-7B-Instruct-v0.2 \\
  --tensor-parallel-size 1
```

## Online Inference Router

The platform now supports online inference routing via `POST /platform/chat`.

- **Evaluation-driven routing:** the router scores candidate backends (`vllm`, `openai`, `mock`) using weighted quality and performance metrics (`pass_rate`, `hallucination_rate`, `p95_latency_ms`, `tokens_per_sec_avg`).
- **Cache-aware backend selection:** repeated system/prefix prompts trigger a prefix-cache heuristic that gives a routing bonus to `vllm`.
- **Shadow evaluation workflow:** 10% of requests are mirrored to an alternate backend for side-by-side latency/score comparison, and summary output is written to `artifacts/proof/shadow_eval_summary.json`.

Every online routing decision is appended to `artifacts/platform_jobs/routing_decisions.jsonl`, and `/platform/chat` returns routing metadata (`selected_backend`, `routing_score`, `cache_hint_used`) for observability.

## Canary Routing and Automatic Rollback

The online inference router now supports a safe canary rollout path for backend upgrades through:

- **Canary activation endpoints:** `POST /platform/canary/start`, `GET /platform/canary/status`, and `POST /platform/canary/stop` manage canary lifecycle and expose live policy/status.
- **Traffic splitting:** when a canary is active, a deterministic percentage of requests (`canary_percent`) is routed to the candidate backend while the remainder stays on baseline.
- **Live metric comparison:** candidate and baseline p95 latency plus candidate pass/hallucination rates are continuously tracked during live traffic.
- **Automatic rollback:** candidate routing is rolled back to baseline if latency exceeds `max_p95_latency_ms`, pass rate drops below `min_pass_rate`, or hallucination rate exceeds `max_hallucination_rate`.
- **Audit artifacts:** request-level canary decisions are appended to `artifacts/platform_jobs/canary_decisions.jsonl` and a current summary is persisted in `artifacts/proof/canary_summary.json`.

`/platform/chat` now includes `canary_applied`, `active_backend`, and `rollback_triggered` fields to make rollout behavior visible to clients and observability workflows.
