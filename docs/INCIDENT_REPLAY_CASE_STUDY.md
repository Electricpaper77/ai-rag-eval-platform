# Gate 19 — Incident Replay Lab

This isolated validation path adds a small FastAPI gateway in front of the existing Go worker pair. A caller-supplied trace/correlation ID is forwarded gateway → worker and is present in both services' structured logs. `worker-b` deterministically returns exactly three bounded HTTP 503 responses after `FAIL_AFTER=20`; subsequent probes demonstrate recovery. The Python/FastAPI evaluator remains unchanged.

Run from `distributed/` with Docker Compose: `docker compose up --build -d`, then `python incident_replay.py`. The script records raw request timestamps, HTTP outcomes, sample count, concurrency, duration, p50/p95/p99, throughput, error rate, trace continuity, timeline, root cause, mitigation, and observed recovery probe duration in `distributed/evidence/incident_report.json`; `incident_report.html` is recruiter-readable.

CI is `.github/workflows/gate19-incident-replay.yml`. It has bounded timeouts, explicit exit-code files, Compose logs, Go build/test/vet/race checks, evaluator regression, and `if: always()` artifact upload. Results must be linked only after an observed workflow run.

Observed run: [workflow 39708577381](https://github.com/Electricpaper77/ai-rag-eval-platform/actions/runs/39708577381), commit `7a0169cb7b4470ea8f5ec46a093ed9ed54d46218`, [evidence artifact 12396491128](https://github.com/Electricpaper77/ai-rag-eval-platform/actions/runs/39708577381/artifacts/12396491128). Ubuntu 24.04 runner, Go 1.22.12, Docker Engine 28.0.4. All recorded exit codes were `0`; evaluator regression was `7 passed`. Machine-readable Gate 19 evidence is [gate19.json](../evidence/infrastructure/gate19.json); the canonical Gate 17 registry remains fixed at gates 1–16.

| Scenario | Sample / concurrency | p50 ms | p95 ms | p99 ms | Throughput req/s | Error rate | Duration s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Healthy worker-a | 40 / 4 | 28.925169 | 34.424467 | 34.569113 | 128.086603 | 0% | 0.312289 |
| Injected worker-b | 40 / 4 | 28.134216 | 32.654879 | 37.045323 | 140.387833 | 7.5% (3/40) | 0.284925 |
| Recovered worker-a | 20 / 4 | 27.157565 | 29.427741 | 29.427741 | 143.352312 | 0% | 0.139516 |

Trace continuity was 100% in all three scenarios. Observed recovery probe duration was 7.018291 ms. The injected incident was exactly three HTTP 503 responses after the worker-b threshold.

Limits: this is local disposable container evidence, not production infrastructure. GPU fields are simulated labels only; they are not physical NVIDIA DCGM measurements and make no GPU-performance claim.
