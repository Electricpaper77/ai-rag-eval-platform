# Gate 19 — Incident Replay Lab

This isolated validation path adds a small FastAPI gateway in front of the existing Go worker pair. A caller-supplied trace/correlation ID is forwarded gateway → worker and is present in both services' structured logs. `worker-b` deterministically returns exactly three bounded HTTP 503 responses after `FAIL_AFTER=20`; subsequent probes demonstrate recovery. The Python/FastAPI evaluator remains unchanged.

Run from `distributed/` with Docker Compose: `docker compose up --build -d`, then `python incident_replay.py`. The script records raw request timestamps, HTTP outcomes, sample count, concurrency, duration, p50/p95/p99, throughput, error rate, trace continuity, timeline, root cause, mitigation, and observed recovery probe duration in `distributed/evidence/incident_report.json`; `incident_report.html` is recruiter-readable.

CI is `.github/workflows/gate19-incident-replay.yml`. It has bounded timeouts, explicit exit-code files, Compose logs, Go build/test/vet/race checks, evaluator regression, and `if: always()` artifact upload. Results must be linked only after an observed workflow run.

Limits: this is local disposable container evidence, not production infrastructure. GPU fields are simulated labels only; they are not physical NVIDIA DCGM measurements and make no GPU-performance claim.
