# Platform Summary (Recruiter-Facing)

## Architecture explanation
This repository demonstrates a lightweight platform-oriented GenAI stack:

1. **Client requests** enter the FastAPI API layer.
2. **Router** applies policy-aware model selection based on latency, quality tier, and health signals.
3. **Inference runtime** executes the chosen backend (`vllm`, `openai`, or `mock`).
4. **Metrics + logs** are emitted to JSONL artifacts for traceable platform behavior.
5. **Benchmark artifacts** provide proof-style outputs for evaluation and performance workflows.

## Benchmark summary
- Dataset: `datasets/eval_dataset_v2.jsonl` (200 prompts across reasoning/retrieval/safety/latency categories).
- Platform summary endpoint: `GET /platform/summary`.
- Summary fields: `models_available`, `last_benchmark_time`, `avg_latency_ms`, `success_rate`, `total_jobs_run`.

## Routing example output
Example route decision shape:

```json
{
  "selected_model": "vllm",
  "routing_reason": "Balanced routing policy selected"
}
```

## Sample job log entries
`artifacts/platform_jobs/job_runs.jsonl` rows include lifecycle-friendly fields:

```json
{"job_id":"req-001","model_used":"vllm","latency_ms":742.5,"success":true,"timestamp":"2026-04-05T00:00:00+00:00"}
{"job_id":"req-002","model_used":"mock","latency_ms":210.3,"success":true,"timestamp":"2026-04-05T00:00:01+00:00"}
{"job_id":"req-003","model_used":"openai","latency_ms":1120.8,"success":false,"timestamp":"2026-04-05T00:00:02+00:00"}
```
