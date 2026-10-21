# Distributed-systems evidence case study

## Scope

AgentTrust IQ keeps its Python/FastAPI deterministic evaluation engine as the release baseline. This change adds a small Go HTTP worker under `distributed/` to make concurrency and failure behavior measurable locally, without a paid cloud dependency.

## Design

- Two local containers use the same stateless Go binary.
- `worker-b` injects exactly three 503 responses after `FAIL_AFTER` requests.
- Each request emits structured JSON logs with request id, latency, and an explicit `gpu_event_source=simulated` label.
- A dependency-free Python load generator emits p50/p95/p99 latency, throughput, and error rate from observed requests.

## Validation workflow

The isolated workflow is `.github/workflows/gate15-distributed-runtime-validation.yml`. It runs `go build ./distributed/...`, `go test ./distributed/...`, `go vet ./distributed/...`, and `CGO_ENABLED=1 go test -race ./distributed/...`, then starts Compose, verifies `/healthz` and `/fanout`, records normal/concurrent/failure-injection/recovery measurements, and runs the existing evaluator regression subset with a 180-second timeout. Every command writes an exit-code file or captured output. A GitHub Actions run URL and artifact link must be added after the workflow is dispatched and observed.

## Results

No benchmark numbers are included yet. The authoring environment did not have a running Docker daemon or Go compiler, and the initial Python baseline command did not complete within the observation window. Run the commands in `distributed/README.md` and paste the raw JSON, compose logs, test output, and `git rev-parse HEAD` here. Recovery time is the measured interval from the first injected 503 to the first subsequent successful probe; it must be recorded, not estimated.

## GPU measurement boundary

The worker's GPU field is a simulation marker used to make the evidence boundary visible. It is not DCGM data. A physical measurement would require an NVIDIA GPU host and DCGM exporter; this repository makes no such claim.
