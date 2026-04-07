# GPU Developer Platform Demo

This repository demonstrates a self-service GPU platform workflow for Kubernetes-first AI workloads with Slurm portability artifacts.

## architecture

- FastAPI control plane (`/platform/jobs`) receives job specs.
- Pre-flight validation checks compute/storage/network guardrails before admission.
- Lifecycle tracking persists job state transitions and runtime metadata.
- Platform artifacts are stored under `artifacts/platform/*.jsonl`.
- Slurm bridge mock emits translated submission records for HPC portability.

## self-service workflows

1. Submit a workload via `POST /platform/jobs`.
2. Platform runs pre-flight checks and writes `preflight_results.jsonl`.
3. Accepted jobs move through `queued -> admitted -> running -> succeeded`.
4. Jobs can be listed with `GET /platform/jobs` and inspected by ID.

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

Checks produce pass/fail plus reason codes:

- `MISSING_IMAGE`
- `INVALID_GPU_COUNT`
- `MISSING_RESOURCE_LIMITS_REQUESTS`
- `MISSING_PROBES`
- `INVALID_STORAGE`
- `MISSING_NETWORK_POLICY_REF`

Results are appended to `artifacts/platform/preflight_results.jsonl`.

## job monitoring

- `GET /platform/jobs`
- `GET /platform/jobs/{job_id}`

Tracked fields include:

- `status`
- `states`
- `timestamps`
- `duration_seconds`
- `retry_count`
- `failure_reason`
- `assigned_node`

## post-mortem analysis

Use persisted JSONL artifacts for root-cause and timeline reconstruction:

- `artifacts/platform/jobs.jsonl`
- `artifacts/platform/preflight_results.jsonl`
- `artifacts/platform/slurm_submissions.jsonl`

## kubernetes templates

Template examples are in `k8s/templates/platform/`:

- `inference-template.yaml`
- `eval-batch-template.yaml`
- `training-style-template.yaml`
- `pdb-example.yaml`
- `network-policy-example.yaml`

Each workload template includes `nvidia.com/gpu`, readiness/liveness probes, PVC mount, node selector, and tolerations.

## storage/networking

Storage and scheduling are provided in each template via:

- `persistentVolumeClaim` mounts
- `storage_class`/`pvc_size` checks at submission time
- network policy reference validation against `network-policy-example.yaml`

## observability

Exported Prometheus metrics:

- `platform_jobs_submitted_total`
- `platform_jobs_failed_total`
- `platform_job_duration_seconds`
- `platform_preflight_failures_total`
- `platform_queue_depth`
- `platform_distributed_jobs_total`
- `platform_admission_rejections_total`
- `platform_priority_queue_depth{priority_class=...}`
- `platform_parallelism_config_total`

Grafana proof placeholder is at `artifacts/observability/grafana_proof_placeholder.md`.

## slurm portability

Submitted platform jobs are translated into Slurm-style artifacts and appended to:

- `artifacts/platform/slurm_submissions.jsonl`

This enables straightforward comparison of Kubernetes-native and HPC scheduler submission semantics.
