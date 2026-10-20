# AgentTrust IQ v1.0.0

## Release Scope

AgentTrust IQ v1.0.0 is a portfolio/research release demonstrating reproducible AI reliability and infrastructure validation. It is intended to be reviewed and reproduced from the repository and its CI evidence.

## Validated Capabilities

- LLM/RAG reliability evaluation with deterministic evidence.
- Kubernetes workload lifecycle operations, Helm/GitOps, and Terraform validation.
- Observability/SLO validation, distributed inference, canary/rollback, autoscaling/capacity, resilience/chaos, and disaster recovery.
- Supply-chain controls, node lifecycle operations, scheduling/preemption/multi-tenancy, and Linux/cgroup CPU throttling and OOM diagnostics.
- Evidence and claims verification with machine-readable registries and bounded audits.

## Verification

See the [architecture](ARCHITECTURE.md), [infrastructure case study](INFRASTRUCTURE_CASE_STUDY.md), [evidence summary](INFRASTRUCTURE_EVIDENCE_SUMMARY.md), and [canonical evidence registry](../evidence/infrastructure/gates.json). The final Gate 19 workflow records the exact tested SHA, fresh HTTP smoke results, regression counts, and artifact digest.

## Known Limitations

AMD/ROCm hardware validation tooling is implemented, but real AMD GPU execution remains blocked pending access to qualifying hardware.

Not claimed:

- Not claimed: production deployment.
- Not claimed: managed-cloud operation.
- Not claimed: production Slurm.
- Not claimed: MI300 execution.
- Not claimed: multi-GPU execution.
- Not claimed: production-scale infrastructure.
