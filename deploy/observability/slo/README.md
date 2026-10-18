# AgentTrust Gate 5 SLOs

`agenttrust-slo.yaml` defines deterministic SLO thresholds for the isolated kind
runtime validation. The workflow evaluates availability, error rate, and p95
latency using Prometheus data from the running AgentTrust workload.

These are CI test settings only. They are not production SLO commitments and do
not represent customer traffic, cloud monitoring, or production MTTR.
