# AgentTrust IQ infrastructure case study

AgentTrust IQ is a model-agnostic reliability and evaluation platform. I extended it with reproducible Kubernetes workload execution, Helm/GitOps lifecycle checks, scheduling and capacity experiments, observability and SLO evidence, resilience testing, disaster-recovery exercises, supply-chain controls, distributed inference, and Linux resource-pressure diagnostics.

The evidence is intentionally bounded: the strongest results are CI runtime or disposable kind-cluster execution. Selected measured proof includes a Gate 16 regression result of 321 passed and 1 xfailed, cgroup v2 CPU-throttling counters, real OOMKilled/exit-137 evidence, Kubernetes node lifecycle recovery, and scheduler/tenant-capacity checks.

AMD/ROCm wording: **Built a strict AMD ROCm hardware-validation pipeline with no CPU fallback; execution remains pending access to qualifying AMD GPU hardware.** No AMD GPU workload execution, MI300 result, or production infrastructure result is claimed.

This is a reproducible engineering portfolio with explicit limitations, not a claim of employer production ownership or a substitute for a production change-control record.
