# Screenshot Checklist

Capture these manually before sharing the repo or portfolio page.

| Screenshot | Suggested filename | What to capture |
|---|---|---|
| Focused AgentTrust tests | `screenshots/pytest_agenttrust_2_passed.png` | Terminal output for `python -m pytest tests/test_agenttrust_demo.py -q` showing `2 passed`. |
| Pytest collection | `screenshots/pytest_128_collected.png` | Terminal output for `python -m pytest --collect-only -q` showing `128 tests collected`. |
| Full-suite status | `screenshots/pytest_full_suite_status.png` | Complete `python -m pytest -q` summary showing `99 passed, 28 failed, 1 xfailed`; do not present the full suite as green. |
| FastAPI docs page | `screenshots/fastapi_docs.png` | Browser view of `/docs`, ideally showing `/v1/chat/completions`, `/evaluate`, `/metrics`, or platform routes. |
| Metrics output | `screenshots/metrics_output.png` | Browser or terminal output for `/metrics` showing eval, inference, security, or GPU metrics. |
| Cloud Run service page | `screenshots/cloud_run_service.png` | Cloud Run service overview if deployed. If not currently deployed, skip this screenshot rather than staging a fake claim. |
| JSONL artifact sample | `screenshots/jsonl_artifact_sample.png` | Open `docs/artifacts/eval_runs/eval_runs.jsonl` or `docs/artifacts/eval_summary.json` with visible run data/checksums. |
| README validation status | `screenshots/readme_validation_status.png` | README section showing `Validation Status` and proof links. |

Keep screenshots current with the latest local validation numbers before using them in applications.
