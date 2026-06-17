# Proof Guide

This is the shortest evidence path for AI Solutions Engineer, LLM Evaluation, and Applied GenAI reviewers.

## Scope

- The Vercel page is a static project walkthrough.
- The FastAPI service runs locally.
- Evaluation metrics come from controlled fixtures and synthetic artifacts.
- Cost values are estimates and no paid model API is required.
- GPU and workload-management signals use simulated providers by default.

## Reproduce the Core Evaluation

```bash
python -m pytest tests/test_agenttrust_demo.py -q
python -m pytest --collect-only -q
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Example request:

```bash
curl -s http://localhost:8000/demo/agenttrust-iq
```

## Evaluation Evidence

| Evidence set | Records | Pass rate | Hallucination rate | Citation precision | Refusal accuracy |
|---|---:|---:|---:|---:|---:|
| Controlled hiring smoke run | 6 | 100.0% | 0.0% | 100.0% | 100.0% |
| Checksum-backed combined evidence | 131 | 97.0% | 0.8% | 83.3% | 83.3% |

The six-case hiring run is a deterministic smoke test. The combined evidence report includes that guardrail sample plus a 125-record historical synthetic evaluation artifact. These results are not production traffic or independent model benchmarks.

## Exact Proof Artifacts

| Artifact | What it proves |
|---|---|
| `docs/artifacts/eval_runs/hiring_eval.jsonl` | Per-case records and summary row for the six-case run |
| `docs/artifacts/eval_runs/hiring_eval_summary.json` | Machine-readable hiring-run metrics |
| `docs/artifacts/eval_summary.json` | Combined metrics and SHA256 input checksums |
| `docs/artifacts/eval_summary.md` | Human-readable 131-record evidence report |
| `docs/security_eval_report.md` | Historical security methodology report; its source fixture and dedicated tests are not present in this checkout |
| `docs/artifacts/metrics_sample.txt` | Prometheus-format metric evidence |
| `docs/artifacts/load_test_results.json` | Local load-test results |
| `docs/artifacts/otel_traces.jsonl` | Trace evidence |
| `tests/test_eval_harness.py` | Hiring-run artifact contract tests |
| `tests/test_agenttrust_demo.py` | Current AgentTrust workflow and Command Center contract tests |

## Controlled Hiring Metrics

Source: `docs/artifacts/eval_runs/hiring_eval_summary.json`

| Metric | Result | Qualification |
|---|---:|---|
| Total cases | 6 | Deterministic fixtures |
| Eval pass rate | 100.0% | Smoke-run result |
| Hallucination rate | 0.0% | Rule-based fixture result |
| Citation precision | 100.0% | Citation-required fixtures |
| Refusal accuracy | 100.0% | Unsafe-request and injection fixtures |
| Evaluator p95 latency | 0.159 ms | Local scoring time, not model latency |
| Estimated cost/request | $0.00000654 | Mock estimate, no vendor API |

## Local Load-Test Evidence

Source: `docs/artifacts/load_test_results.json`

| Metric | Result |
|---|---:|
| Requests | 290 |
| Successful checks | 284 |
| Check pass rate | 97.9% |
| HTTP failure rate | 2.07% |
| Request rate | 9.39 req/sec |
| p95 successful-response latency | 53.44 ms |

## Validation

Current local working-tree result:

```text
Focused AgentTrust demo tests: 2 passed
Repository collection: documented local collection proof
Full legacy/shared fixture suite: 103 passed, 28 failed, 1 expected xfail; not the official judge validation path
```

Run:

```bash
python -m pytest tests/test_agenttrust_demo.py -q
python -m pytest --collect-only -q
```

Portfolio materials reference 145+ passing tests as the current regression claim, separate from
the focused judge path and collection count above. Refresh these counts whenever code or tests
change, and do not describe a local result as hosted production validation.

## Resume-Safe Claim

Built a FastAPI RAG and LLM evaluation platform with deterministic citation, hallucination,
refusal, prompt-injection, and PII checks; generated checksum-backed JSONL evidence across 131
fixture records, exposed Prometheus metrics, and added a focused, reproducible AgentTrust demo
validation path.
