# Feature Spec: Resilient Regression Evaluation JSONL Logging

## Goal
Build a **resilient regression evaluation logging feature** aligned with production AI infrastructure patterns.

## Requirements
- **files to modify:**
  - `backend/app/eval/regression.py`
  - `tests/test_regression_eval.py`
- **expected inputs/outputs:**
  - **Input:** `run_regression_eval(query_fn, dataset, variants, top_k, run_id, artifact_dir)`.
  - **Output:** summary dict with `run_id`, `created_at`, `output_file`, per-variant metrics, and overall metrics; plus JSONL artifact at `artifacts/eval_runs/regression_<run_id>.jsonl`.
- **metrics to log:**
  - `latency_ms`, `tokens_generated`, `tokens_per_second`
  - `citation_coverage_rate`, `refusal_rate`, `hallucination_rate`
  - `fallback_used` count and error metadata in row-level logs.
- **compatibility constraints:**
  - Preserve existing route contract in `/eval/regression`.
  - Keep JSONL row-level fields backward compatible (`prompt`, `answer`, `latency_ms`, `tokens_generated`, `tokens_per_second`, `eval_pass`) while adding new observability fields.
- **failure fallback behavior:**
  - If `query_fn` raises an exception or returns non-dict payload, write a safe fallback row with:
    - placeholder answer,
    - empty citations,
    - zero tokens,
    - `fallback_used=true`,
    - `error_type` and `error_message` for debugging.

## Acceptance criteria
- **command to test:**
  - `pytest -q tests/test_regression_eval.py`
- **expected artifact path:**
  - `artifacts/eval_runs/regression_<run_id>.jsonl`
  - (tests use a temp `artifact_dir` override)
- **expected fields in JSONL:**
  - `run_id`, `created_at`, `variant`, `case_id`
  - `prompt`, `prompted_query`, `answer`, `top_k`
  - `citation_count`, `latency_ms`, `tokens_generated`, `tokens_per_second`
  - `fallback_used`, `error_type`, `error_message`, `eval_pass`
