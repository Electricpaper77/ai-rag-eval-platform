# AgentTrust IQ — Reproducible Reliability Evaluation

## Problem

AgentTrust IQ turns reliability checks into explicit release, block, or escalate decisions with replayable JSONL evidence. The focused proof path covers groundedness and citation behavior, uncertainty around unverifiable claims, PII handling, prompt-injection refusal, unsafe-request refusal, and citation support for benchmark claims.

## Evaluation architecture

The existing deterministic harness in `app/eval_harness.py` builds six controlled cases, evaluates them with the repository's reliability evaluator, records one JSON object per case plus a summary record, and applies the thresholds in `eval_thresholds.yaml`.

## Recorded result

The Gate 32H reproduction ran at source SHA `deddce135660a5ffb9c62864ac485aa1b910cab1` using Python 3.11.9 and the isolated `.venv`.

| Signal | Result |
| --- | ---: |
| Cases passed | 6 / 6 |
| Evaluation pass rate | 100% |
| Hallucination rate | 0% |
| Citation precision | 100% |
| Refusal accuracy | 100% |
| Local evaluator p95 | 0.245 ms |
| Threshold decision | PASS |

The run is deterministic fixture evidence with `estimated_mock_no_vendor_api`. The latency value is local evaluator runtime, not provider, API, RAG, end-to-end, GPU, or production performance.

## Reliability controls demonstrated

- Citation coverage checks
- Uncertainty handling for unverifiable claims
- PII leakage checks
- Prompt-injection refusal
- Unsafe credential-theft refusal
- Explicit pass/fail and failure-reason fields
- Threshold-based release decision
- Per-case JSONL audit evidence

## Validation

The established focused suite produced **21 passed, 0 failed, 0 skipped**. Portfolio verification passed, and `git diff --check` exited successfully with only EOL conversion warnings.

## Reproduction

From the repository root with the existing environment:

```powershell
.\.venv\Scripts\python.exe -c "from app.eval_harness import run_eval_harness; run_eval_harness(output_path='artifacts/gate32h/repro_hiring_eval.jsonl', summary_path='artifacts/gate32h/repro_hiring_eval_summary.json', run_id='gate32h-repro-20261114')"
```

Evidence files:

- `docs/artifacts/gate32h/hiring_eval.jsonl` — published 6 case records plus 1 summary record
- `docs/artifacts/gate32h/hiring_eval_summary.json` — published aggregate metrics
- `docs/artifacts/gate32h/provenance.json` — published source, environment, command, threshold, and artifact hashes
- `docs/artifacts/gate32h/recruiter_case_study.md` — this published case study

## Limitations

- Six deterministic fixture cases are not customer-production telemetry.
- No external model provider, live API, RAG service, managed SaaS environment, or physical GPU was used.
- Source SHA and environment provenance were added to this Gate 32 package; historical canonical artifacts remain unchanged.
- The checkout is EOL-dirty but content-verified; it is not Git-clean.
- Public-demo availability does not independently verify backend production behavior.
