# AgentTrust IQ 2.0 Reproducible Benchmark Report

Last verified against local working tree at base commit `5596c3b`.

## Benchmark Command

```bash
python scripts/run_regression_tests.py
python scripts/check_eval_thresholds.py --artifact runs/agenttrust_regression_eval.jsonl
```

## Current Local Result

Source artifact: `runs/agenttrust_regression_eval.jsonl`

| Metric | Current value | Measurement method |
| --- | ---: | --- |
| Total regression cases | 6 | Count of `record_type: case` rows |
| Passed cases | 6 | Case rows with `pass: true` |
| Eval pass rate | 1.0 | `passed_cases / total_cases` |
| Hallucination rate | 0.0 | Summary emitted by regression harness |
| Citation precision | 1.0 | Average citation precision in harness summary |
| Refusal accuracy | 1.0 | Average refusal accuracy in harness summary |
| p95 latency | 0.189ms | Summary emitted by regression harness |
| Cost/request estimate | 0.00000654 USD | Deterministic token estimate, not vendor billing |
| Threshold decision | PASS | `scripts/check_eval_thresholds.py` result |

## Scope

This benchmark validates deterministic reliability logic, not live model quality or external API
performance. Cost values are estimates from local token counting and must not be presented as cloud
billing records.

## Covered Regression Categories

- Citation grounding pass
- Hallucination uncertainty pass
- PII sanitization pass
- Prompt-injection refusal pass
- Unsafe request refusal pass
- Benchmark claim citation pass
