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

Observed Gate 15B run: [GitHub Actions run 39566204592](https://github.com/Electricpaper77/ai-rag-eval-platform/actions/runs/39566204592), commit `d51d31f8921a251667f3a923e3a026a3349747eb`, Ubuntu 24.04.5, Go 1.22.12, Docker Engine 28.0.4. The [uploaded evidence artifact](https://github.com/Electricpaper77/ai-rag-eval-platform/actions/runs/39566204592/artifacts/12329722630) contains raw logs, exit codes, and JSON measurements.

| Scenario | Sample / concurrency | p50 ms | p95 ms | p99 ms | Throughput req/s | Error rate | Duration s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Normal worker-a | 200 / 1 | 0.468716 | 0.525459 | 0.590638 | 1943.702466 | 0.0% | 0.102896 |
| Concurrent worker-a | 200 / 20 | 4.710589 | 10.804165 | 12.593503 | 2880.954481 | 0.0% | 0.069421 |
| Failure-injected worker-b | 40 / 10 | 2.583072 | 4.126963 | 4.218759 | 2108.914355 | 7.5% (3/40) | 0.018967 |

Recovery was measured as **5 ms**, from the post-failure probe start to the first successful `/work` response. Worker-to-worker `/fanout` returned HTTP 200 and `gpu_event_source: simulated`. Go build, test, vet, and CGO-enabled race detection each exited `0`; evaluator regression exited `0` with `7 passed`.

The first workflow attempt failed at container build with `undefined: log`; the minimal import fix produced the passing run above. No merge was performed.

## GPU measurement boundary

The worker's GPU field is a simulation marker used to make the evidence boundary visible. It is not DCGM data. A physical measurement would require an NVIDIA GPU host and DCGM exporter; this repository makes no such claim.
