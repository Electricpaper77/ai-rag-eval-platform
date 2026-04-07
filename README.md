# GPU Developer Platform Demo

A backend-focused demo of GPU platform orchestration responsibilities: submission APIs, pre-flight validation, lifecycle management, governance controls, observability, and portability across Kubernetes and HPC-style scheduling systems.

## Architecture overview

Core modules:
- `gpu_platform/api.py`: self-service platform APIs.
- `gpu_platform/job_orchestrator.py`: lifecycle simulation, admission control, artifact persistence.
- `gpu_platform/preflight_checks.py`: validation and reason-code generation.
- `gpu_platform/metrics.py`: Prometheus metric instrumentation.
- `gpu_platform/inference_backend.py`: runtime abstraction layer (`InferenceBackend`, mock backend, vLLM-style placeholder).

## Self-service workflows

### Submit GPU workload
- `POST /platform/jobs`
- Unified schema supports inference, batch-eval, and training-style workloads.

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
- `platform_preflight_failures_total`

## HPC portability layer

Slurm bridge mapping persists:
- `partition`, `gpus`, `cpus`, `memory`, `time_limit`

## Proof artifacts

All platform JSONL artifacts are persisted under `artifacts/platform_jobs/`:
- `jobs.jsonl`
- `preflight_results.jsonl`
- `distributed_jobs.jsonl`
- `slurm_submissions.jsonl`
- `postmortem_reports.jsonl`

## Validation commands

```bash
pytest
python -m py_compile gpu_platform/*.py backend/app/*.py
```
