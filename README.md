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

## Multi-runtime inference architecture

```text
Client
  -> FastAPI gateway
      -> runtime router
          -> vLLM backend
          -> Triton backend
```

Supporting multiple runtimes keeps the gateway flexible when teams need to balance quality, latency, and infrastructure constraints across model serving stacks. vLLM can be retained for OpenAI-compatible serving while Triton can be introduced for GPU-optimized workflows that benefit from explicit control of inference request payloads.

Triton integration in this repository focuses on architecture clarity:

- OpenAI-style chat inputs are normalized before runtime dispatch.
- Triton requests are translated to `POST /v2/models/{model_name}/infer` payloads.
- Responses are returned in a shared normalized shape (`output`, `tokens_out`, `latency_ms`) so evaluation and routing logic stay backend-agnostic.

Why this matters for GPU inference optimization:

- Triton supports dynamic batching patterns that can improve throughput under bursty request traffic.
- Runtime abstraction allows benchmarking and routing policies to compare latency/throughput behaviors without changing client contracts.
- Operators can keep one API surface while iterating on backend deployment strategy.

Resume-proof highlights:

- implemented runtime abstraction layer supporting multiple GPU inference backends
- integrated Triton inference server adapter for optimized batching workloads
- standardized OpenAI-compatible interface across inference runtimes
- generated benchmark artifacts comparing inference latency characteristics

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

The FastAPI service now includes an evaluation dashboard that ingests JSONL artifacts from:

- `artifacts/evals/*.jsonl`
- `artifacts/routing/*.jsonl`
- `artifacts/benchmarks/*.jsonl`

Run metadata is stored in:

- `artifacts/run_metadata.json`

### Dashboard API

- `GET /dashboard/summary`
- `GET /dashboard/runs`
- `GET /dashboard` (simple HTML table view)

`GET /dashboard/summary` returns:

```json
{
  "eval_pass_rate": 0.8,
  "hallucination_rate": 0.1,
  "citation_precision": 0.85,
  "p95_latency_ms": 201.3,
  "cost_per_request": 0.0026
}
```

`GET /dashboard/runs` returns experiment run records including:

- `model_version`
- `prompt_version`
- `dataset_version`
- `timestamp`
- `metrics` (`eval_pass_rate`, `hallucination_rate`, `citation_precision`, `refusal_accuracy`, `p50_latency_ms`, `p95_latency_ms`, `tokens_per_second`, `cost_per_request`)

The repository includes example evaluation data at `artifacts/evals/test_eval.jsonl` (50 rows).

### Screenshot

Add a dashboard screenshot to `docs/screenshots/eval_dashboard.png` after running the UI locally.


## AI Job Orchestration Layer

This repository includes a simple GPU job orchestration abstraction to model platform-style inference and evaluation workflows without claiming a live cluster scheduler.

```text
user request
-> job submission api
-> routing policy
-> runtime backend
-> metrics collection
-> job artifact logs
```

### Recruiter-ready highlights

- implemented GPU workload orchestration abstraction
- built job lifecycle tracking system
- simulated platform-style batch inference workflows
- generated structured job artifacts for reproducibility

## Autoscaling simulation

```text
job queue
-> concurrency controller
-> runtime backend
-> metrics
```

This repository now includes a lightweight autoscaling simulation layer for GPU inference workflows. The goal is architecture realism: show how queue pressure can drive scaling decisions without making claims about production autoscaler behavior.

Why autoscaling matters for GPU workloads:

- GPU serving is capacity constrained, and saturation can quickly increase request latency when incoming traffic spikes.
- Queue growth is often the first signal that inference capacity is under-provisioned for current workload intensity.
- Capacity-aware controllers help platforms decide when to scale up, hold, or scale down to balance responsiveness and cost.

How queue latency impacts inference performance:

- As concurrency rises beyond the configured active GPU worker limit, requests accumulate in backlog before execution.
- Queue delay compounds end-to-end latency even if model execution speed is stable.
- This simulation models that effect so benchmark artifacts can capture latency sensitivity under 5/10/20 concurrent jobs.

How platforms manage capacity:

- `k8s/hpa.yaml` models a HorizontalPodAutoscaler with CPU and request-concurrency metrics for inference deployments.
- `platform/concurrency_controller.py` provides queue-aware scale actions (`scale_up`, `hold`, `scale_down`).
- `scripts/run_load_scenario.py` generates `artifacts/load_test/load_summary.json` for repeatable load validation output.

Recruiter proof bullets:

- simulated GPU workload autoscaling behavior using concurrency-aware job controller
- modeled queue latency impact across varying concurrency levels
- generated structured load artifacts supporting performance validation

### Job orchestration API

- `POST /platform/jobs`
- `GET /platform/jobs/{job_id}`
- `GET /platform/jobs`

Job runs are persisted as JSON under `artifacts/job_runs/`.

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


## GPU Runtime Benchmark Proof

Use `scripts/run_real_gpu_benchmark.py` to run 50 sequential OpenAI-compatible chat completion requests against a live vLLM runtime and save a machine-readable benchmark artifact at:

- `artifacts/benchmarks/gpu_real_run.json`

The script measures and records:

- `total_time_sec`
- `requests_per_sec`
- `avg_latency_ms`
- `p95_latency_ms`
- `tokens_per_second`

After running the benchmark, retrieve the latest recorded artifact through:

- `GET /benchmark/latest`

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

## Multi-Model Selection Logic

The platform supports evaluation-driven routing by selecting the best model from:

- `artifacts/evals/*.jsonl`
- `artifacts/benchmarks/*.jsonl`
- `artifacts/run_metadata.json`

The selector computes per-run metrics:

- `eval_pass_rate`
- `hallucination_rate`
- `citation_precision`
- `p95_latency_ms`
- `tokens_per_second`
- `cost_per_request`

Scoring formula:

- `quality_score = eval_pass_rate - hallucination_rate + citation_precision`
- `latency_score = 1 / p95_latency_ms`
- `cost_score = 1 / cost_per_request`
- `final_score = (quality_weight * quality_score) + (latency_weight * latency_score) + (cost_weight * cost_score)`

Default weights:

- `quality_weight = 0.5`
- `latency_weight = 0.3`
- `cost_weight = 0.2`

Selection output is persisted to `artifacts/platform_jobs/best_model.json` and exposed by:

- `GET /platform/best-model`

A leaderboard view is also available at:

- `GET /dashboard/leaderboard`

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
- **Shadow evaluation workflow:** production requests can trigger background shadow execution (`force_shadow=true` or `quality_tier=balanced`) without changing user-facing output.

Every online routing decision is appended to `artifacts/platform_jobs/routing_decisions.jsonl`, and `/platform/chat` returns routing metadata (`selected_backend`, `routing_score`, `cache_hint_used`) for observability.

## Canary Routing and Automatic Rollback

The online inference router now supports a safe canary rollout path for backend upgrades through:

- **Canary activation endpoints:** `POST /platform/canary/start`, `GET /platform/canary/status`, and `POST /platform/canary/stop` manage canary lifecycle and expose live policy/status.
- **Traffic splitting:** when a canary is active, a deterministic percentage of requests (`canary_percent`) is routed to the candidate backend while the remainder stays on baseline.
- **Live metric comparison:** candidate and baseline p95 latency plus candidate pass/hallucination rates are continuously tracked during live traffic.
- **Automatic rollback:** candidate routing is rolled back to baseline if latency exceeds `max_p95_latency_ms`, pass rate drops below `min_pass_rate`, or hallucination rate exceeds `max_hallucination_rate`.
- **Audit artifacts:** request-level canary decisions are appended to `artifacts/platform_jobs/canary_decisions.jsonl` and a current summary is persisted in `artifacts/proof/canary_summary.json`.

`/platform/chat` now includes `canary_applied`, `active_backend`, and `rollback_triggered` fields to make rollout behavior visible to clients and observability workflows.


## Shadow Evaluation Workflow

Shadow evaluation captures real online routing outputs from a candidate model while keeping the primary response path unchanged.

**Flow diagram**

`request → router → primary response → async shadow run → JSONL log → evaluation summary`

**Artifacts**

- Request-level shadow logs: `artifacts/shadow_runs/shadow_eval.jsonl`
- Aggregated summary: `artifacts/proof/shadow_eval_summary.json`

**How to run analysis**

```bash
python scripts/run_shadow_eval_analysis.py
```

The API endpoint `GET /eval/shadow-summary` also exposes the computed metrics (`agreement_rate`, `avg_latency_delta_ms`, and `avg_cost_delta`) from the JSONL log.

## Platform Architecture Signals

```text
Client
  -> Router
      -> Model Policy
          -> Inference Runtime
              -> Metrics
                  -> Benchmark Artifacts
```

This flow is intentionally simple and recruiter-readable while still showing practical platform abstraction boundaries used in ML infrastructure teams.

## GPU Workload Template

Two Kubernetes templates are included for infrastructure signaling:

- `k8s/gpu-job.yaml`: batch-style inference/eval `Job` with `nvidia.com/gpu: 1`, CPU/memory requests+limits, `restartPolicy: Never`, and container args that call an inference endpoint.
- `k8s/gpu-deployment.yaml`: online inference API `Deployment` with `readinessProbe`, `livenessProbe`, monitoring labels, and explicit compute resource requests.

### Why both patterns matter

- **`nvidia.com/gpu` usage:** expresses explicit accelerator scheduling constraints in cluster orchestration.
- **Batch jobs vs deployments:** batch jobs are better for finite benchmark/eval workloads; deployments are better for continuously available inference APIs.
- **Routing abstraction layer:** model policy logic decouples request intent (latency/quality/cost) from concrete backend selection, which mirrors real platform teams.

## Prometheus Operator Scraping

A Prometheus Operator `ServiceMonitor` is a Kubernetes custom resource that tells Prometheus which Services to scrape for metrics and how to scrape them (endpoint port, path, and interval).

In this repo, `k8s/servicemonitor.yaml` selects Services labeled for monitoring and scrapes the API metrics endpoint exposed on `http-metrics` at `/metrics` every `30s`. This connects Prometheus to the inference/evaluation API without hardcoding targets in Prometheus config.

### Platform-proof updates

- Added Kubernetes-native metrics scraping via Prometheus Operator ServiceMonitor.
- Exposed inference service metrics for latency and throughput monitoring.
- Standardized service labels/selectors to support reliable monitoring discovery.
- Documented operational verification steps for platform observability.

### Common failure point

The most common issue is a label/selector mismatch between the Deployment pod labels, Service selectors/labels, and ServiceMonitor selectors. If these are not aligned, Prometheus Operator will not discover scrape targets.

### Verification commands

```bash
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/servicemonitor.yaml

kubectl get deploy ai-rag-eval-api --show-labels
kubectl get svc ai-rag-eval-api --show-labels
kubectl get svc ai-rag-eval-metrics --show-labels
kubectl get servicemonitor ai-rag-eval-metrics -o yaml
kubectl get endpoints ai-rag-eval-api

kubectl port-forward svc/ai-rag-eval-api 8080:8080
curl -s http://127.0.0.1:8080/metrics | head
```
