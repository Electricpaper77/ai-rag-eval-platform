# Recruiter evidence summary

- Preserved the existing Python/FastAPI evaluation engine and its deterministic evidence contract.
- Added a minimal Go concurrent worker with structured logs, bounded failure injection, two-container local topology, and a reproducible load-test command.
- The benchmark schema covers p50/p95/p99 latency, throughput, error rate, recovery time, exact commands, and Git SHA; values remain blank until executed on a host with Go and Docker available.
- Race detection command: `go test -race ./...`.
- GPU honesty: events are explicitly labeled simulated; no physical DCGM measurement is claimed.
- Cost boundary: local containers only; no paid cloud deployment.
