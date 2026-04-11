# GPU Developer Platform Demo

A backend-focused demo of GPU platform orchestration responsibilities: submission APIs, pre-flight validation, lifecycle management, governance controls, observability, and portability across Kubernetes and HPC-style scheduling systems.

## Architecture overview

Core modules:
- `gpu_platform/api.py`: self-service platform APIs.
- `gpu_platform/job_orchestrator.py`: lifecycle simulation, admission control, artifact persistence.
- `gpu_platform/preflight_checks.py`: validation and reason-code generation.
- `gpu_platform/metrics.py`: Prometheus metric instrumentation.
- `gpu_platform/inference_backend.py`: inference provider abstraction used by chat completion flows.
- `gpu_platform/runtime_backends.py`: platform runtime backend layer (`InferenceRuntime`, `MockRuntime`, `VLLMRuntime`, Triton stub).

## Self-service workflows

### Submit GPU workload
- `POST /platform/jobs`
- Unified schema supports inference, batch-eval, and training-style workloads.

## Distributed GPU Workload Topology

The platform accepts distributed topology metadata on `POST /platform/jobs`:

- `replicas`: number of replicated workers.
- `gpu_per_replica`: GPUs attached to each replica.
- `tensor_parallel`: tensor-shard degree per model execution stage.
- `pipeline_parallel`: pipeline stage count.
- `data_parallel`: data-parallel group count.
- `placement_group`: placement affinity bucket for topology-aware scheduling.
- `worker_group`: logical worker grouping label.
- `priority_class`: queue class (`latency-sensitive`, `balanced`, `batch`).

Derived and validated behavior:

- `total_gpu_requested = replicas * gpu_per_replica`.
- `tensor_parallel >= 1`, `pipeline_parallel >= 1`, `data_parallel >= 1`.
- `total_gpu_requested > 0`.
- Parallelism product (`tensor_parallel * pipeline_parallel * data_parallel`) cannot exceed `total_gpu_requested` unless explicitly marked with `oversubscribed=false` and a non-empty reason code.

Queue and admission model:

- Priority order is `latency-sensitive` > `balanced` > `batch`.
- FIFO ordering is preserved within each priority class.
- Admission quotas enforce:
  - `MAX_GPUS_PER_JOB = 8`
  - `MAX_REPLICAS_PER_JOB = 8`
  - `MAX_QUEUE_DEPTH = 32`

Rejections emit structured reason codes:

- `quota_exceeded`
- `invalid_parallelism_config`
- `invalid_replica_count`
- `invalid_gpu_request`
- `queue_full`
- `unsupported_priority_class`

Artifacts:

- Distributed topology records: `artifacts/platform_jobs/distributed_jobs.jsonl`
- Admission rejections: `artifacts/platform_jobs/admission_rejections.jsonl`
- Core lifecycle history: `artifacts/platform/jobs.jsonl`

## pre-flight checks
### List jobs
- `GET /platform/jobs`

### Inspect job lifecycle
- `GET /platform/jobs/{job_id}`
- Returns: `status`, `submission_time`, `start_time`, `end_time`, `retry_count`, `assigned_node`, `failure_reason`.

Lifecycle states used by the platform: `queued`, `admitted`, `running`, `succeeded`, `failed`.

## Unified job specification

Required/primary fields:
- `job_id`, `workload_type`, `image`, `model`, `command`, `env`
- `gpu_count`, `cpu`, `memory`, `replicas`, `retry_limit`, `timeout_seconds`

Distributed config:
- `tensor_parallel`, `pipeline_parallel`, `gpu_per_replica`

Storage config:
- `pvc_size`, `storage_class`, `mount_path`

Scheduling config:
- `node_selector`, `tolerations`, `priority_class`, `queue`

Validation-specific fields:
- `readiness_probe`, `liveness_probe`, `network_isolation`

## Job lifecycle model

`submit_job(...)` flow:
1. Persist pre-flight result.
2. Apply admission constraints:
   - `MAX_GPUS_PER_JOB = 4`
   - `MAX_REPLICAS = 8`
   - `MAX_QUEUE_DEPTH = 32`
3. Mark failed jobs with reason codes and generate postmortem artifacts.
4. Mark admitted jobs succeeded in this simulation and persist Slurm bridge artifacts.

## Pre-flight validation

Checks include:
- `gpu_count > 0`
- CPU/memory limits present
- container image format validity
- retry policy validity
- storage configuration validity
- readiness/liveness probes
- network isolation configuration presence
- distributed parallelism validity

Reason codes include:
- `invalid_gpu_request`
- `missing_storage_config`
- `invalid_probe_config`
- `quota_exceeded`
- `invalid_parallelism_config`

## Kubernetes workload templates

- `k8s/gpu-inference.yaml`
- `k8s/gpu-batch.yaml`
- `k8s/gpu-training.yaml`

Each includes GPU limits, PVC mount, node selection/tolerations, readiness/liveness probes, and restart policy.

## Storage and networking assumptions

- PVC example: `k8s/pvc-gpu-workload.yaml`
  - parameter placeholders: PVC size, mount path, storage class.
  - assumes CSI dynamic provisioning.
- Network policy example: `k8s/network-policy-gpu-isolation.yaml`
  - assumes CNI enforcement of ingress/egress isolation.

## Observability metrics

Exposed at `GET /metrics`:
- `platform_jobs_submitted_total`
- `platform_jobs_failed_total`
- `platform_job_duration_seconds`
- `platform_queue_depth`
- `platform_distributed_jobs_total`
- `platform_admission_rejections_total`
- `platform_priority_queue_depth{priority_class=...}`
- `platform_parallelism_config_total`
- `platform_preflight_failures_total`
- `platform_runtime_selection_total`
- `platform_runtime_validation_failures_total`
- `platform_vllm_config_generated_total`
- `platform_runtime_deployments_total`

## Platform Observability Insights

Operators can transform raw platform metrics and lifecycle artifacts into a structured health report with:

```bash
python scripts/generate_platform_report.py
```

Generated artifacts:
- `artifacts/platform_jobs/platform_failure_summary.json`
- `artifacts/platform_jobs/platform_health_report.json`

The report captures:
- `queue_pressure_level` (`low`, `moderate`, `high`) derived from `platform_queue_depth`.
- `routing_distribution` percentages for `latency_pool`, `throughput_pool`, and `distributed_pool`.
- `failure_summary` covering failure reason frequency, retry frequency, and admission rejection reasons.
- `parallelism_summary` with average `replicas`, `tensor_parallel`, and `gpu_per_replica`, plus inefficient topology hints.
- `runtime_usage_summary` from runtime selection records.

Why these signals matter:
- **Queue depth** is a first-line reliability indicator: sustained high depth means admission pressure and likely latency growth.
- **Routing distribution** validates pool balancing: heavy concentration in one pool can indicate policy drift, bad defaults, or capacity skew.
- **Parallelism configuration** catches underutilized distributed jobs (for example, large GPU requests still running with `replicas=1` and `tensor_parallel=1`), which wastes cluster throughput.

## HPC portability layer

Slurm bridge mapping persists:
- `partition`, `gpus`, `cpus`, `memory`, `time_limit`

## Inference Routing Layer

The demo includes a workload-aware inference routing layer in `gpu_platform/request_router.py` that focuses on platform decisions (runtime + GPU pool selection), not model internals.

### Workload classification inputs

Routing decisions consider:
- `latency_budget_ms`
- `priority_class`
- `gpu_required`
- `parallelism_config`
- live `queue_depth`
- `historical_failure_rate`

### Routing decision policies

High-level policy rules:
- latency-sensitive requests (`latency_budget_ms <= 900` or `priority_class=latency-sensitive`) route to `latency_pool`.
- batch workloads (`workload_type=batch` or `priority_class=batch`) route to `throughput_pool`.
- larger parallel jobs (`tensor_parallel * data_parallel >= 8`) route to `distributed_pool`.
- non-GPU jobs route to `shared_pool`.
- resilience fallback routes to `shared_pool` during deep queue / elevated failure rates.

### GPU pool abstraction

The platform simulates pool capacity and runtime mapping:
- `latency_pool` → `mock_vllm`
- `throughput_pool` → `mock_triton`
- `distributed_pool` → `mock_ray`
- `shared_pool` → `mock_vllm`

Each routing decision is persisted to:
- `artifacts/platform_jobs/routing_decisions.jsonl`

### KV-cache policy strategy

The router emits `kv_cache_strategy`:
- `distributed` for large contexts (e.g., `context_tokens >= 4096`).
- `reuse` for repeated prompts or default interactive inference.
- `isolated` for batch jobs.

### Platform optimization logic and API behavior

- `POST /platform/jobs` now includes a `routing` block with `gpu_pool`, `runtime`, `kv_cache_strategy`, and `batching_strategy`.
- Prometheus exports routing telemetry:
  - `platform_routing_decisions_total`
  - `platform_routing_latency_bucket`
  - `platform_kv_cache_strategy_total`
  - `platform_gpu_pool_selection_total`

## Proof artifacts

All platform JSONL artifacts are persisted under `artifacts/platform_jobs/`:
- `jobs.jsonl`
- `preflight_results.jsonl`
- `distributed_jobs.jsonl`
- `slurm_submissions.jsonl`
- `postmortem_reports.jsonl`
- `runtime_selections.jsonl`
- `runtime_validation_results.jsonl`
- `vllm_runtime_configs.jsonl`
- `runtime_deployments.jsonl`

## Validation commands

```bash
pytest
python -m py_compile gpu_platform/*.py backend/app/*.py
```


## Runtime Backend Layer

Platform jobs include runtime planning so orchestration decisions can map onto executable inference backends without adding frontend or prompt UX complexity.

### Why runtime selection exists

Different job classes need different runtime behavior:
- latency-sensitive inference jobs prefer `VLLMRuntime` for low-latency serving semantics.
- distributed workloads that use tensor/pipeline parallelism prefer `VLLMRuntime`.
- unsupported or incomplete runtime configs fall back to `MockRuntime` with structured reason codes.
- batch/eval jobs use `MockRuntime` by default unless they are vLLM-compatible.

### Runtime outputs and topology mapping

`VLLMRuntime` emits config records containing:
- `model`, `served_model_name`
- `tensor_parallel_size`, `pipeline_parallel_size`, `data_parallel_size`
- `nnodes`, `node_rank`, `distributed_executor_backend`
- `max_model_len`, `gpu_memory_utilization`, `kv_cache_policy`, `priority_class`, `gpu_pool`, `runtime_name`

Parallelism maps directly from platform fields:
- `tensor_parallel` -> `tensor_parallel_size`
- `pipeline_parallel` -> `pipeline_parallel_size`
- `data_parallel` -> `data_parallel_size`

### Runtime artifacts

- runtime selections: `artifacts/platform_jobs/runtime_selections.jsonl`
- runtime validation results: `artifacts/platform_jobs/runtime_validation_results.jsonl`
- vLLM runtime configs: `artifacts/platform_jobs/vllm_runtime_configs.jsonl`
- runtime deployment specs: `artifacts/platform_jobs/runtime_deployments.jsonl`

`POST /platform/jobs` responses include additive runtime metadata under `job["runtime"]`:
- `runtime_name`
- `runtime_plan`
- `runtime_config_path`
- `deployment_config_path`
- `validation`

## Production Inference Observability Pipeline

This feature adds a production-style inference telemetry pipeline with modular components, structured artifact persistence, and performance-centric observability.

### Directory structure

```text
backend/app/observability/
├── __init__.py
├── artifact_store.py
├── models.py
├── performance.py
└── service.py

tests/
└── test_inference_observability_pipeline.py

artifacts/inference_events/
└── year=YYYY/month=MM/day=DD/inference_events.jsonl
```

### Implementation files

- `backend/app/observability/models.py`: typed event schema for request context + performance metrics.
- `backend/app/observability/performance.py`: phase-level latency decomposition (queue, TTFT, decode) and decode throughput metrics.
- `backend/app/observability/artifact_store.py`: date-partitioned JSONL persistence for scalable artifact ingestion.
- `backend/app/observability/service.py`: orchestration layer that builds context, computes metrics, emits Prometheus metrics, and stores events.
- `backend/app/inference.py`: runtime inference flow now records structured telemetry per request.
- `backend/app/metrics.py`: additional counters/histograms for end-to-end pipeline observability.

### Tests

- `tests/test_inference_observability_pipeline.py` validates:
  - phase-level performance metric calculations,
  - artifact persistence under partitioned paths,
  - telemetry correlation via `request_id`,
  - metrics surface exposure on `/metrics`.

### Performance metrics captured

Each inference event records realistic serving-path metrics:

- `latency_ms` (end-to-end)
- `queue_time_ms` (admission/dispatch delay)
- `ttft_ms` (time-to-first-token)
- `decode_time_ms` (token generation phase)
- `tokens_out`
- `tokens_per_second` (decode throughput)

Prometheus metrics added:

- `inference_pipeline_events_total{runtime,model,status}`
- `inference_queue_time_ms{runtime,model}`
- `inference_ttft_ms{runtime,model}`
- `inference_decode_time_ms{runtime,model}`
- `inference_decode_throughput_tps{runtime,model}`

## Architecture

This repo now includes a **production-style local inference slice** that preserves the existing FastAPI app while adding OpenAI-compatible inference semantics and observability artifacts:

- **API layer**: `POST /v1/chat/completions` in `backend/app/main.py`, delegated to `backend/app/inference.py`.
- **Runtime abstraction**: `backend/runtimes/base.py` and `backend/runtimes/mock_runtime.py`.
- **Backend selection**: `INFERENCE_BACKEND=mock` (default) for deterministic CPU-only inference simulation.
- **Metrics**: Prometheus counters/histogram in `backend/app/metrics.py`, exported at `GET /metrics`.
- **Artifacts**:
  - request logs: `artifacts/inference_logs.jsonl`
  - benchmark summary: `artifacts/benchmark_summary.json`

## OpenAI-compatible API

`POST /v1/chat/completions`

Request example:

```json
{
  "model": "mock-llm",
  "messages": [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Hello"}
  ],
  "max_tokens": 256,
  "temperature": 0.7
}
```

Response shape:

- `id`, `object`, `created`, `model`
- `choices[0].message.role/content`
- `choices[0].finish_reason`
- `usage.prompt_tokens/completion_tokens/total_tokens`

## Metrics exposed

`GET /metrics` includes:

- `llm_requests_total{backend,status}`
- `llm_tokens_total{backend,status}`
- `llm_request_latency_seconds{backend,status}`

## Benchmark methodology

Run:

```bash
python scripts/run_benchmark.py --base-url http://127.0.0.1:8000 --requests 25 --model mock-llm
```

Method:
- issues N sequential `POST /v1/chat/completions` calls
- captures end-to-end per-request latency
- aggregates:
  - p50 latency
  - p95 latency
  - requests/sec
  - tokens/sec
  - success_rate
- writes reproducible artifact to `artifacts/benchmark_summary.json`

## Proof artifacts

The following files provide portfolio-quality proof points:

- `artifacts/inference_logs.jsonl`: one JSONL event per inference request
- `artifacts/benchmark_summary.json`: benchmark KPIs for a run
- `tests/test_chat_endpoint.py`: OpenAI-compatible schema validation
- `tests/test_metrics.py`: Prometheus scrape-format validation
- `tests/test_runtime.py`: deterministic runtime behavior validation

## Local run instructions

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start API:

```bash
INFERENCE_BACKEND=mock uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

3. Test endpoint:

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"mock-llm",
    "messages":[{"role":"system","content":"You are helpful"},{"role":"user","content":"Say hello"}],
    "max_tokens":128,
    "temperature":0.7
  }'
```

4. Run benchmark:

```bash
python scripts/run_benchmark.py --base-url http://127.0.0.1:8000 --requests 25
```

## Model Selection Infrastructure

The platform now includes production-style model routing and benchmark leaderboard generation designed for decision engineering workflows.

### Tradeoff decision logic

- Static model candidates live in `config/model_registry.yaml` with quality, latency, and cost metadata.
- `gpu_platform/request_router.py` supports policy-driven model routing for chat-style requests:
  - `fast`: picks the lowest-latency eligible model.
  - `balanced`: computes weighted tradeoff score (`0.5*quality - 0.3*latency_norm - 0.2*cost_norm`).
  - `high_quality`: picks the highest quality score.
- Budget constraints (`latency_budget_ms`, `max_cost`) filter candidate models before policy selection.

### Benchmark-driven routing

- `scripts/run_model_eval.py` executes the same JSONL prompt dataset against every registered model.
- The runner is mock-friendly and deterministic (hash-based simulation), so it does not require a GPU runtime.
- Results are materialized in `artifacts/model_eval/leaderboard.json` and can be served via `GET /leaderboard`.

### Evaluation reproducibility

- Evaluation outcomes are deterministic per model/prompt pair, enabling repeatable CI checks.
- Artifact output path is stable (`artifacts/model_eval/leaderboard.json`) for downstream dashboards and regression gates.
- Prometheus now exports model-level routing telemetry:
  - `model_requests_total{model=...}`
  - `model_latency_seconds_bucket{model=...}`
  - `model_selection_count{policy=...}`
