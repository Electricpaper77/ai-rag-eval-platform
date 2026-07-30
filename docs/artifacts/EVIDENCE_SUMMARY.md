# Evidence Summary

Homepage headline metrics use only **Canonical controlled hiring run** (6 deterministic cases). Other suites are coverage or fixture evidence and are not combined into a benchmark.

## Canonical controlled hiring run
- Type: `canonical`; cases: 6; passed: 6; failed: 0
- Execution: no external provider; deterministic fixture harness. local deterministic evaluator runtime; not model, API, RAG, or end-to-end latency
- Artifacts: `docs/artifacts/eval_runs/hiring_eval.jsonl`, `docs/artifacts/eval_runs/hiring_eval_summary.json`
- Reproduce: `python -m app.eval_harness.run_eval_harness`

## Supplemental deterministic security coverage
- Type: `simulated`; cases: 40; passed: 40; failed: 0
- Execution: deterministic simulated tool requests. fixture replay latency only; not production performance
- Artifacts: `artifacts/agenttrust_iq/cyber_tool_firewall_eval.jsonl`
- Reproduce: `checked-in deterministic fixture artifact`

## Mock provider evaluation
- Type: `mock`; cases: 50; passed: None; failed: None
- Execution: mock/offline fixture; no authenticated NVIDIA request. no provider or hardware latency recorded
- Artifacts: `eval/nvidia_nemotron_pack.jsonl`
- Reproduce: `python -m app.eval.run --provider mock --suite eval/nvidia_nemotron_pack.jsonl --output artifacts/latest`

## Combined integrity/evidence records
- Type: `supplemental`; cases: 131; passed: 127; failed: 4
- Execution: mixed historical fixture records. mixed historical artifacts; not comparable to canonical run
- Artifacts: `docs/artifacts/eval_summary.json`
- Reproduce: `python scripts/summarize_eval.py`
