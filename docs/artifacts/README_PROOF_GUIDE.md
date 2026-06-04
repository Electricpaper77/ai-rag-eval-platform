# Recruiter Proof Guide

This guide lists the exact screenshots to capture for the 60-second recruiter proof package. Do not create placeholder or fake screenshots; capture only real local output after running the documented commands.

## Screenshot Checklist

| Screenshot filename | What to capture | What it proves | Place it here |
|---|---|---|---|
| `evaluate_openapi.png` | FastAPI `/docs` page showing the `/evaluate` endpoint. | The project exposes a reviewer-visible LLM evaluation API. | `screenshots/evaluate_openapi.png` |
| `evaluate_response.png` | Successful `/evaluate` JSON response for the prompt-injection refusal example in `README.md` or `PROOF.md`. | The evaluator returns structured pass/fail scoring, reason fields, metrics, and a run ID. | `screenshots/evaluate_response.png` |
| `eval_dashboard.png` | `/dashboard` proof cards after local eval artifacts exist. | The project summarizes evaluation evidence in a hiring-manager-readable view. | `screenshots/eval_dashboard.png` |
| `hiring_eval_jsonl.png` | Terminal or editor preview of `docs/artifacts/eval_runs/hiring_eval.jsonl`, including the final summary row. | The eval harness writes auditable JSONL proof artifacts for controlled deterministic fixtures. | `screenshots/hiring_eval_jsonl.png` |
| `hiring_eval_summary.png` | Terminal or editor preview of `docs/artifacts/eval_runs/hiring_eval_summary.json`. | The headline proof metrics are machine-readable and clearly labeled, including mock-estimated cost. | `screenshots/hiring_eval_summary.png` |
| `pytest_full_suite.png` | Terminal output from `python -m pytest -q` showing `133 passed, 1 xfailed`. | The repository has regression coverage for the documented proof surface. | `screenshots/pytest_full_suite.png` |

## Suggested Caption

AI RAG evaluation platform with deterministic `/evaluate`-equivalent fixtures, JSONL audit artifacts, regression tests, and recruiter-readable proof metrics: 100% controlled fixture pass rate, 0% hallucination rate, 100% citation precision, 100% refusal accuracy, 0.159 ms local p95 evaluator latency, and mock-estimated $0.00000654/request cost with no vendor API call.

## Scope Language

Use this wording when posting screenshots or describing the project publicly:

These metrics are controlled deterministic eval fixture results from local proof artifacts. They are not production traffic claims, live customer metrics, or vendor benchmark claims.
