# AgentTrust IQ GCP Terraform foundation

This directory is a production-shaped, validation-first Terraform foundation for a future AgentTrust IQ deployment on Google Cloud GKE. Gate 4 models the infrastructure and runs deterministic static validation; it does not provision cloud resources.

## Architecture

```text
Dedicated VPC
  └─ Regional custom subnet
      ├─ Private Google Access
      ├─ Pod secondary range
      └─ Service secondary range

Private regional GKE cluster
  ├─ CPU node pool (default, autoscaled, repaired/upgraded)
  └─ Optional GPU node pool (disabled by default; declarative only)

Artifact Registry Docker repository: agenttrust-iq
Workload Identity: Kubernetes service account -> Google service account
```

## Module boundaries

- `modules/network`: custom VPC, subnet, private Google access, and secondary ranges.
- `modules/gke`: private regional cluster, Workload Identity enablement, CPU pool, optional GPU pool, logging, and managed-Prometheus hook.
- `modules/artifact_registry`: Docker repository metadata and URL.
- `modules/workload_identity`: Google service account, least-privilege federation binding, and optional accessor binding to an existing Secret Manager secret.

The root module composes these modules without hardcoded project IDs. The CPU pool is the default. The GPU pool is disabled unless explicitly enabled and does not prove AMD, ROCm, or GPU execution.

## Security model

- Private nodes and a private control-plane CIDR are modeled.
- No public node IP dependency is introduced.
- Workload Identity uses `roles/iam.workloadIdentityUser` for the named Kubernetes service account.
- Secret Manager access is optional and scoped to one existing secret with `roles/secretmanager.secretAccessor`; no secret value is managed.
- No service-account keys, credentials, Owner roles, or Editor roles are generated.
- Terraform state and credentials are excluded from evidence artifacts.

## Observability hooks

GKE system/workload logging is enabled in the cluster module. Managed Prometheus collection is configurable with `enable_managed_prometheus` and defaults to false. Prometheus/Grafana/Loki are not installed by Gate 4.

## Validation and plan boundary

The Gate 4 workflow runs Terraform formatting, provider initialization without a backend, validation, deterministic Python assertions, TFLint, and Checkov. It attempts `terraform plan -refresh=false` with a non-secret placeholder project ID. If Google provider authentication is unavailable, the workflow records `PLAN: HOLD — authentication/provider limitation` while keeping static IaC acceptance separate.

No GCP resources were provisioned by Gate 4. A real `terraform apply` against an authorized project is explicitly out of scope.
