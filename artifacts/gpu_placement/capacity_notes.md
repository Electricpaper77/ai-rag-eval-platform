# Capacity control notes

This repository uses static examples to model recruiter-readable Kubernetes capacity control patterns.

## Concurrency assumptions

- Inference deployment uses 2 replicas with 1 GPU each.
- Batch evaluation is assumed to run up to 2 jobs in parallel.
- Namespace quota caps aggregate GPU requests/limits at 8.

## Placement assumptions

- **Inference:** `nodeSelector + toleration` to keep low-latency traffic on predictable GPU nodes.
- **Batch:** `nodeAffinity + toleration` to keep asynchronous workloads on allowed GPU pools while preserving scheduler flexibility.

## Scope note

No live cluster claims are made. All manifests and artifacts are templates for platform design discussion and interviews.
