# Infrastructure evidence summary

| Area | Executed Proof | Evidence Level | Result |
| --- | --- | --- | --- |
| Kubernetes platform | Four workloads, security controls, recovery, and regression checks | DISPOSABLE_CLUSTER_RUNTIME | PASS |
| Helm/GitOps | Install, upgrade, rollback, drift, and self-heal | DISPOSABLE_CLUSTER_RUNTIME | PASS |
| Scheduling/capacity | Preemption, quotas, LimitRange, taints/tolerations, recovery | DISPOSABLE_CLUSTER_RUNTIME | PASS |
| Observability/SLOs | Metrics, alerts, incident and error-budget scenarios | CI_RUNTIME | PASS |
| Resilience | Dependency, latency, 5xx, readiness, and network recovery | DISPOSABLE_CLUSTER_RUNTIME | PASS |
| Disaster recovery | Isolated backup/restore and recovery evidence | DISPOSABLE_CLUSTER_RUNTIME | PASS |
| Supply chain | Provenance, release, dependency, and image policy checks | CI_RUNTIME | PASS |
| Linux pressure | cgroup v2 throttling, OOMKilled/137, and recovery | DISPOSABLE_CLUSTER_RUNTIME | PASS |
| AMD/ROCm hardware | Validation pipeline prepared; qualifying AMD runner unavailable | BLOCKED | HOLD |

The registry in [`evidence/infrastructure/gates.json`](../evidence/infrastructure/gates.json) is the machine-readable source of truth. It deliberately does not claim employer production ownership, managed cloud administration, or real AMD GPU execution.
