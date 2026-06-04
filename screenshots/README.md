# Screenshot Checklist

Capture these manually before sharing the repo or portfolio page.

| Screenshot | Suggested filename | What to capture |
|---|---|---|
| Full pytest passing | `screenshots/pytest_131_passed.png` | Terminal output for `python -m pytest -q` showing `131 passed, 1 xfailed`. |
| Security eval passing | `screenshots/security_eval_passed.png` | Terminal output for `python -m pytest tests/test_security_eval.py -q -s` showing `5 passed`. |
| Evidence integrity passing | `screenshots/evidence_integrity_passed.png` | Terminal output for `python -m pytest tests/test_generate_eval_evidence.py -q` showing `3 passed`. |
| FastAPI docs page | `screenshots/fastapi_docs.png` | Browser view of `/docs`, ideally showing `/v1/chat/completions`, `/evaluate`, `/metrics`, or platform routes. |
| Metrics output | `screenshots/metrics_output.png` | Browser or terminal output for `/metrics` showing eval, inference, security, or GPU metrics. |
| Cloud Run service page | `screenshots/cloud_run_service.png` | Cloud Run service overview if deployed. If not currently deployed, skip this screenshot rather than staging a fake claim. |
| JSONL artifact sample | `screenshots/jsonl_artifact_sample.png` | Open `docs/artifacts/eval_runs/eval_runs.jsonl` or `docs/artifacts/eval_summary.json` with visible run data/checksums. |
| README validation status | `screenshots/readme_validation_status.png` | README section showing `Validation Status` and proof links. |

Keep screenshots current with the latest local validation numbers before using them in applications.
