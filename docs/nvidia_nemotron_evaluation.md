# NVIDIA Nemotron Evaluation

The NVIDIA pack is isolated from AgentTrust IQ's deterministic controlled metrics. It never changes the canonical hiring-evaluation claims and writes no metrics until a real authenticated NIM request has completed.

Run this five-case, one-model, low-credit smoke test after setting `NVIDIA_API_KEY` locally:

```powershell
$env:NVIDIA_MODELS='YOUR_NVIDIA_API_CATALOG_MODEL'
$env:NVIDIA_CONCURRENCY='1'
python -m nvidia_eval.runner --smoke-test --models $env:NVIDIA_MODELS --max-requests 5 --resume
```

The runner fixes `temperature` to `0`, caches responses by SHA-256 of model, prompt, and parameters, retries temporary server errors and 429s, and exits gracefully after persistent quota exhaustion. A real run creates `artifacts/model-comparison.jsonl`, `artifacts/benchmark-summary.json`, `artifacts/failure-analysis.csv`, and `artifacts/run-manifest.json`. The NVIDIA Evaluation page remains intentionally empty until those artifacts exist.
## Offline-safe validation

`nvidia_eval/` is isolated from ChromaDB, vector retrieval, and the full RAG app. It sends the OpenAI-compatible NVIDIA NIM chat-completions payload only when a user later runs it with `NVIDIA_API_KEY` in the environment. Keys are never written to artifacts, frontend responses, logs, or exceptions; `.env` is ignored and `.env.example` keeps `NVIDIA_API_KEY` blank.

Run the deterministic no-network validation with `python scripts/validate_nvidia_eval_pack.py`. It verifies the 50 JSONL cases, local scoring, request format (including temperature zero), SHA-256 cache identity, retry/429 recovery, quota stopping, malformed output, timeout, missing-key and redaction behavior. The future authenticated smoke command is `NVIDIA_MODELS=<model> python -m nvidia_eval.runner --smoke-test --max-requests 5`.

The cache hashes model, prompt, and parameters; `--resume` reuses completed cases and `--max-requests` bounds cost. Expected real-run evidence is JSONL output, benchmark summary, failure analysis, and a run manifest. No NVIDIA benchmark has been run: dashboard status is `not_run` and it intentionally provides no latency, pass rate, citation precision, or comparison values. The repository-wide suite remains subject to its pre-existing native ChromaDB dependency limitation.
