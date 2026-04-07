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

Grafana proof placeholder is at `artifacts/observability/grafana_proof_placeholder.md`.

## slurm portability

Submitted platform jobs are translated into Slurm-style artifacts and appended to:

- `artifacts/platform/slurm_submissions.jsonl`

This enables straightforward comparison of Kubernetes-native and HPC scheduler submission semantics.
