# AgentTrust IQ 2.0 Completion Checklist

Last updated: local working tree, pre-commit.

## Gate Status

| Gate | Status | Evidence |
| --- | --- | --- |
| Gate 0: repository and production-readiness audit | Complete | Repo, branch, deployment, tests, and docs inspected. Vercel static deployment verified separately from FastAPI API. |
| Gate 1: evaluation engine | Complete locally | Deterministic `/evaluate` supports hallucination, groundedness, citation precision, refusal accuracy, prompt adherence proxies, PII, and prompt-injection checks. Focused tests pass. |
| Gate 2: security | Complete locally | Prompt-injection blocking, PII redaction, unsafe-compliance detection, and adversarial regression tests added. |
| Gate 3: observability | Complete locally | `/evaluate` JSONL emits trace IDs, latency, throughput, error flag, token estimate, and cost/request estimate. Dashboard aggregation covers p50/p95, throughput, error rate, and cost/request. |
| Gate 4: release gates | Complete locally | Threshold gate returns PASS, BLOCK, or ESCALATE and checks quality, safety, latency, throughput, citation, and refusal thresholds against generated JSONL evidence. Remote CI run still needs verification after push. |
| Gate 5: dashboard | Complete locally | Dashboard metrics are computed from JSONL/JSON artifacts, `/dashboard/evidence` lists downloadable evidence, and `/dashboard/evidence/{id}` serves only known artifacts. Historical comparisons are available through grouped runs and leaderboard views. |
| Gate 6: production readiness | Complete locally | Health, metrics, OpenAPI, bad-request behavior, env-var docs, Docker, Cloud Build, Procfile, and static Vercel config are covered by tests. Public API deployment still needs independent verification after deployment. |
| Gate 7: recruiter evidence | Complete locally | Refreshed architecture diagram, reproducible benchmark report, test report, 90-second demo script, and technical README aligned to verified local facts. |
| Gate 8: local build verification | Complete with Docker daemon caveat | Production-style local API smoke, Python compile, dependency sanity, deployment-config parsing, and Docker context hygiene passed. Docker image build was attempted but blocked because the Docker Desktop Linux engine was not running locally. |
| Gate 11: GitHub Actions | Implemented locally, pending push verification | Production CI workflow now installs dependencies, runs `pip check`, compiles Python, runs regression release gates, executes the full pytest suite, builds the Docker image, and uploads evidence artifacts. GitHub Actions run URL requires explicit push approval. |

## Current Verified Commands

- `python -m pytest -q --basetemp .pytest_tmp` -> 148 passed, 1 expected xfail.
- `python -m pytest smoke_test.py tests/test_smoke.py tests/test_chat_endpoint.py tests/test_metrics.py tests/test_agenttrust_demo.py tests/test_agent_evaluation.py tests/test_security_guardrails.py tests/test_dashboard.py tests/test_dashboard_metrics.py tests/test_eval_dashboard_metrics.py tests/test_eval_harness.py tests/test_schema_and_api.py tests/test_check_eval_thresholds.py tests/test_production_readiness.py -q --basetemp .pytest_tmp` -> 44 passed.
- `python -m pytest tests/test_agent_evaluation.py tests/test_dashboard.py tests/test_eval_harness.py -q --basetemp .pytest_tmp`
- `python -m pytest smoke_test.py tests/test_smoke.py tests/test_chat_endpoint.py tests/test_metrics.py tests/test_agenttrust_demo.py tests/test_agent_evaluation.py tests/test_security_guardrails.py tests/test_dashboard.py tests/test_eval_harness.py tests/test_schema_and_api.py tests/test_check_eval_thresholds.py -q --basetemp .pytest_tmp`
- `python scripts/run_regression_tests.py` -> 6 passed, p95 0.189ms.
- `python scripts/check_eval_thresholds.py --artifact runs/agenttrust_regression_eval.jsonl` -> PASS.
- `python -m pytest tests/test_check_eval_thresholds.py tests/test_eval_harness.py tests/test_agent_evaluation.py tests/test_security_guardrails.py -q --basetemp .pytest_tmp`
- `python -m pytest tests/test_dashboard_metrics.py tests/test_dashboard.py tests/test_eval_dashboard_metrics.py -q --basetemp .pytest_tmp`
- `python -m pytest tests/test_production_readiness.py -q --basetemp .pytest_tmp`
- `python -m pytest --collect-only -q --basetemp .pytest_tmp` -> 149 tests collected.
- `git diff --check` -> passed with Markdown line-ending warnings only.
- `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010` with local HTTP checks -> `/health`, `/metrics`, and `/openapi.json` returned 200.
- `python -m compileall -q app backend gpu_platform scripts tests` -> passed.
- `python -m pip check` -> no broken requirements found.
- `python -c "import json, pathlib, yaml; json.loads(pathlib.Path('vercel.json').read_text()); yaml.safe_load(pathlib.Path('cloudbuild.yaml').read_text()); print('CONFIG_OK')"` -> `CONFIG_OK`.
- `python -m pytest tests/test_production_readiness.py -q --basetemp .pytest_tmp` -> 6 passed.
- `docker build -t agenttrust-iq-local:verify .` -> blocked locally because Docker Desktop Linux engine was unavailable: `dockerDesktopLinuxEngine` pipe not found.
- `python -m gunicorn backend.app.main:app --bind 127.0.0.1:8011 --workers 1 --timeout 120 --worker-class uvicorn.workers.UvicornWorker` -> blocked on native Windows because Gunicorn imports `fcntl`; verify this runtime command in Linux/Docker or CI.
- `python -c "import pathlib, yaml; [yaml.safe_load(path.read_text()) for path in pathlib.Path('.github/workflows').glob('*.yml')]; print('WORKFLOW_YAML_OK')"` -> `WORKFLOW_YAML_OK`.
- Local CI-equivalent checks after Gate 11 workflow repair:
  - `python -m pip check` -> no broken requirements found.
  - `python -m compileall -q app backend gpu_platform scripts tests` -> passed.
  - `python scripts/run_regression_tests.py` -> 6 passed, p95 0.292ms.
  - `python scripts/check_eval_thresholds.py --artifact runs/agenttrust_regression_eval.jsonl` -> PASS.
  - `python -m pytest -q --basetemp .pytest_tmp` -> 148 passed, 1 expected xfail.

## Remaining Before Completion

- Push and verify GitHub Actions release gate against generated `runs/agenttrust_regression_eval.jsonl`.
- Deploy or expose the FastAPI service and verify deployed API behavior, not just static Vercel pages.
- Re-run the supported validation suite after any additional edits and refresh proof artifacts if metrics change.
