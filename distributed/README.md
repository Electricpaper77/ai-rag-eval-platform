# Local distributed worker evidence

This is an isolated Go worker/telemetry slice. The Python/FastAPI evaluator remains unchanged. `worker-a` is healthy; `worker-b` injects three HTTP 503 responses after request 20. Logs are JSON structured events. The `gpu_event_source=simulated` field is deliberate: this is not a physical NVIDIA DCGM measurement.

## Reproduce

Requires Docker Desktop with the Linux daemon running. From `distributed/`:

```bash
docker compose up --build -d
curl -fsS http://127.0.0.1:18080/healthz
curl -fsS http://127.0.0.1:18080/fanout
python load_test.py --url http://127.0.0.1:18080/work --requests 200 --concurrency 20 > before.json
python load_test.py --url http://127.0.0.1:18081/work --requests 200 --concurrency 20 > failure-injected.json
docker compose logs --no-color > compose.log
docker compose down
```

For Go checks, with Go 1.22+ installed:

```bash
go test ./...
go build ./...
go vet ./...
CGO_ENABLED=1 go test -race ./...
go test -race ./...
```

The load test prints measured p50/p95/p99 latency, throughput, and error rate. Recovery time must be measured by a separate timestamped probe after failure injection; no result is claimed until these commands are run. Record the exact `git rev-parse HEAD` alongside the JSON outputs.

## Evidence boundary

This local experiment demonstrates concurrent HTTP work, structured telemetry, controlled failure, and reproducible measurement across two containers. It does not prove GPU utilization, NCCL behavior, DCGM telemetry, or production SLOs. GPU events are simulated labels only; physical DCGM measurements require a configured NVIDIA driver, DCGM exporter, and GPU host.
