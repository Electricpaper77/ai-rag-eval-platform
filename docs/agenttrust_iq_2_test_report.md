# AgentTrust IQ 2.0 Test Report

Last verified against local working tree at base commit `5596c3b`.

## Full Local Validation Suite

Command:

```bash
python -m pytest -q --basetemp .pytest_tmp
```

Verified result:

```text
148 passed, 1 xfailed in 92.71s
```

## Repository Collection

Command:

```bash
python -m pytest --collect-only -q --basetemp .pytest_tmp
```

Verified result:

```text
149 tests collected
```

## Regression Gate

Commands:

```bash
python scripts/run_regression_tests.py
python scripts/check_eval_thresholds.py --artifact runs/agenttrust_regression_eval.jsonl
```

Verified result:

```text
6 of 6 regression cases passed; threshold decision PASS.
```

## Local Build Verification

Commands:

```bash
python -m compileall -q app backend gpu_platform scripts tests
python -m pip check
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
```

Verified result:

```text
Python compile passed.
pip check: No broken requirements found.
/health, /metrics, and /openapi.json returned HTTP 200 from the local production-style server.
Deployment config syntax parsed successfully for vercel.json and cloudbuild.yaml.
Production readiness tests passed, including Docker context hygiene checks for .dockerignore.
```

Docker build command attempted:

```bash
docker build -t agenttrust-iq-local:verify .
```

Result:

```text
Blocked locally because Docker Desktop Linux engine was unavailable: dockerDesktopLinuxEngine pipe not found.
```

Dockerfile runtime command attempted after installing `requirements.txt`:

```bash
python -m gunicorn backend.app.main:app --bind 127.0.0.1:8011 --workers 1 --timeout 120 --worker-class uvicorn.workers.UvicornWorker
```

Result:

```text
Blocked on native Windows because Gunicorn imports fcntl. This command should be verified in Linux/Docker or CI.
```

## Known Gaps

- Remote GitHub Actions must be verified after push.
- Public FastAPI deployment must be independently verified after deployment.
