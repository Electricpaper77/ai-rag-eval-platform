# AgentTrust IQ canonical evidence matrix

This matrix is evidence-first: a capability is marked `PASS` only when the
listed repository file, observed CI artifact, or bounded local command supports
the claim. `DISPOSABLE_CLUSTER_RUNTIME` is not production-cluster evidence.

## Identity and evidence classes

| Item | Exact identity | Evidence class | Status |
| --- | --- | --- | --- |
| Product baseline reviewed for this change | `deddce135660a5ffb9c62864ac485aa1b910cab1` (`origin/main`) | SOURCE_CONTROL | PASS |
| Published synthetic product release | `v1.1.0-rc.1`, source `282501243705111bfff8c1cc07a77bb0aa153beb` | RELEASE_METADATA | PASS |
| Portfolio after PR #5 | `622df7cf08117142afceefa2348fa8eacc818ce3` | SOURCE_CONTROL / CI_RUNTIME | PASS |
| Portfolio public homepage and proof page | `zohaib-mlops-portfolio.vercel.app` | PUBLIC_STATIC_SITE | PASS |
| Physical NVIDIA DCGM telemetry | No physical GPU host evidence | BLOCKED | NOT CLAIMED |

## Infrastructure capabilities

| Capability | Repository evidence | Observed CI/evidence | Status and permitted claim |
| --- | --- | --- | --- |
| Resilience and chaos | `deploy/chaos/`, `tests/test_gate10_resilience.py` | Gate 10 disposable-kind workflow and registry entry | PASS — bounded dependency, latency, 5xx, readiness and network experiments |
| Stateful recovery | `scripts/gate11_backup.py`, `scripts/gate11_restore.py`, `tests/test_gate11_disaster_recovery.py` | Gate 11 disposable recovery evidence | PASS — isolated backup/restore behavior; not production DR |
| Planned node lifecycle | `.github/workflows/gate14-node-lifecycle-ops.yml`, `scripts/gate14_node_lifecycle.py`, `tests/test_gate14_node_lifecycle.py` | Run `39347089135`, artifact `12230849852`, digest `sha256:c8d4ab10415efe1639c4697539187878222fb6f270885f05cdc9e44fc97c63fa` | PASS — cordon/drain, eviction, replacement and continuity in disposable kind |
| Unplanned worker-node loss | Same Gate 14 files on this feature branch; `node-loss-report` requires a surviving worker and rejoining lost node | CI execution required on this feature SHA; local Docker/Kubernetes daemon unavailable | PENDING CI — implementation and 8 focused local tests pass; no cluster PASS claimed yet |
| Scheduler and tenant capacity | `tests/test_gate15_scheduler_multitenancy.py`, `deploy/scheduling/` | Run `39350497727`, artifact `12233466884`, digest `sha256:704f61819bd4ad7666b806c006eeb5fb0c00f5b7be9903de03666f65c2f63d33` | PASS — disposable multi-node scheduling evidence |
| Linux resource pressure | `scripts/gate16_resource_diagnostics.py`, `tests/test_gate16_linux_resource_pressure.py` | Run `39352972429`, artifact `12234710581`, digest `sha256:81538e5551f648e9b913c11c9ae9840e468c0c3ac67607b333d09b835b4b4223` | PASS — cgroup/OOM evidence in disposable runtime |
| Distributed incident replay | `distributed/`, `docs/INCIDENT_REPLAY_CASE_STUDY.md`, `evidence/infrastructure/gate19.json` | Run `39708577381`, artifact `12396491128`, digest `sha256:6568a056e75c26a46fe131e15a12d93cd4b8b45c56de1ad0444372bd9fc59405` | PASS — exact recorded exit codes and synthetic local-container measurements |

## Validation of this change

| Command | Exit/result | Evidence boundary |
| --- | --- | --- |
| `python -m pytest -q tests/test_gate14_node_lifecycle.py` | `0`, `8 passed` | Local deterministic helper/workflow contract tests |
| `python -m pytest -q tests/test_gate10_resilience.py tests/test_gate14_node_lifecycle.py tests/test_gate15_scheduler_multitenancy.py tests/test_gate16_linux_resource_pressure.py` | `0`, `23 passed` | Local deterministic regression subset |
| `python -m py_compile scripts/gate14_node_lifecycle.py` | `0` | Local syntax validation |
| YAML parse of `.github/workflows/gate14-node-lifecycle-ops.yml` | `0`, `WORKFLOW_YAML_OK` | Local workflow syntax validation |
| `git diff --check` | `0` | Local whitespace validation |
| `docker info` / `kubectl cluster-info --request-timeout=5s` | nonzero: Docker Desktop Linux engine and local API unavailable | Local cluster scenario not executed; CI kind run is required |

The new node-loss row must not be promoted to `PASS` until a final feature-SHA
Gate 14 run uploads `node-loss-recovery.json`, health/inference continuity
outputs, node rejoin evidence, and a successful workflow conclusion. The
scenario uses synthetic mock inference only. No production Kubernetes, managed
cloud, commercial SLA/RPO/RTO, or physical GPU/DCGM claim is implied.
