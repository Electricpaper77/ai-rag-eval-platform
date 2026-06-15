# Evaluation Evidence Summary

Generated at: `2026-06-03T23:11:01+00:00`

This report is a checksum-backed evidence index for checked-in eval artifacts. The 6-prompt guardrail run is a reproducible smoke sample with intentional negative controls, not the full benchmark. Larger historical eval artifacts are summarized separately when present.

## Aggregate Metrics

| Metric | Value |
|---|---:|
| Total prompt count | 131 |
| Pass rate | 97.0% |
| Hallucination rate | 0.8% |
| Citation precision | 83.3% |
| Refusal/guardrail accuracy | 83.3% |

## Per-Artifact Evidence

| Label | Artifact | Prompts | Pass rate | Hallucination rate | Citation precision | Refusal/guardrail accuracy |
|---|---|---:|---:|---:|---:|---:|
| guardrail_smoke_sample | `docs/artifacts/eval_runs/eval_runs.jsonl` | 6 | 33.3% | 16.7% | 83.3% | 83.3% |
| historical_eval_benchmark | `docs/artifacts/runs/eval_run_001.jsonl` | 125 | 100.0% | 0.0% | n/a | n/a |

## Input Artifact Checksums

| Artifact | Label | Prompts | SHA256 |
|---|---|---:|---|
| `docs/artifacts/eval_runs/eval_runs.jsonl` | guardrail_smoke_sample | 6 | `94bc8f569f4a3cdb2b29ab69ff2a2cfd0e65db77ed2aebb48522d2e7298a6867` |
| `docs/artifacts/runs/eval_run_001.jsonl` | historical_eval_benchmark | 125 | `7df1a74d01a98b1e7d74457c3353129dbc82019b34632bd05f32389fa41db307` |

Historical generator command:

```bash
python scripts/generate_eval_evidence.py
```

The generation script is not present in this checkout. Use the checked-in JSON and Markdown
summaries as historical checksum-backed evidence, not as a currently reproducible generation step.
