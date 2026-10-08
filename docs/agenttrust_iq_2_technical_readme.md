# AgentTrust IQ 2.0 Technical README

Last verified against local working tree at base commit `5596c3b`.

## What This Platform Does

AgentTrust IQ 2.0 evaluates LLM and agent responses before release. It combines deterministic
evaluation, security guardrails, observability, CI threshold gates, and dashboard evidence.

## Core Capabilities

- Evaluation engine: hallucination risk, groundedness, citation precision, refusal accuracy, prompt
  adherence proxies, PII leakage, and prompt-injection compliance.
- Security: PII redaction for emails, phone numbers, SSNs, and credit-card-like values; prompt
  injection detection; unsafe request refusal checks.
- Observability: JSONL logs with trace IDs, latency, p50/p95 aggregation, throughput, error rate,
  estimated token counts, and estimated cost/request.
- Release gates: configurable PASS, BLOCK, and ESCALATE decisions in CI from `eval_thresholds.yaml`.
- Dashboard: metrics and evidence downloads are computed from JSONL and JSON artifacts, not hardcoded.
- Production readiness: health, metrics, OpenAPI, error handling, env-var docs, Docker, Cloud Build,
  Procfile, and static Vercel behavior are covered by tests.

## Local Quickstart

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Useful endpoints:

- `GET /health`
- `GET /metrics`
- `POST /v1/chat/completions`
- `POST /evaluate`
- `POST /query_guarded`
- `GET /dashboard`
- `GET /dashboard/evidence`

## Reproducible Validation

```bash
python -m pytest smoke_test.py tests/test_smoke.py tests/test_chat_endpoint.py tests/test_metrics.py tests/test_agenttrust_demo.py tests/test_agent_evaluation.py tests/test_security_guardrails.py tests/test_dashboard.py tests/test_dashboard_metrics.py tests/test_eval_dashboard_metrics.py tests/test_eval_harness.py tests/test_schema_and_api.py tests/test_check_eval_thresholds.py tests/test_production_readiness.py -q --basetemp .pytest_tmp
python scripts/run_regression_tests.py
python scripts/check_eval_thresholds.py --artifact runs/agenttrust_regression_eval.jsonl
git diff --check
```

Current verified local results:

- Full local suite: 148 passed, 1 expected xfail.
- Regression benchmark: 6 of 6 passed.
- Threshold gate: PASS.
- Repository collection: 149 tests collected.
- Local build sanity: Python compile passed, `pip check` passed, deployment config syntax parsed, Docker context hygiene is covered by `.dockerignore`, and local production-style API smoke returned HTTP 200 for `/health`, `/metrics`, and `/openapi.json`.
- Docker image build: attempted locally, but blocked because Docker Desktop's Linux engine was not running.
- Dockerfile runtime command: Gunicorn/Uvicorn dependencies import after installing `requirements.txt`; native-Windows Gunicorn execution is blocked by Gunicorn's `fcntl` dependency and should be verified inside Linux/Docker or CI.

## Deployment Status

- Static Vercel walkthrough: deployed and separately verified earlier.
- FastAPI API: verified locally; public API deployment still needs independent verification.
- GitHub Actions: workflow configured; remote run must be verified after push.
