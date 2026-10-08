# AgentTrust IQ 2.0 90-Second Demo Script

## 0-15 Seconds: Positioning

AgentTrust IQ 2.0 is a production-style LLM evaluation and AI agent reliability platform. It does
not just show a chatbot response; it evaluates whether an agent response is grounded, cited,
privacy-safe, injection-resistant, observable, and eligible to ship.

## 15-35 Seconds: Evaluation Engine

Open the local API or dashboard evidence. Show that `/evaluate` records deterministic checks for
hallucination risk, groundedness, citation precision, refusal accuracy, prompt adherence proxies,
PII leakage, and prompt-injection compliance. The output is written as JSONL evidence with trace ID,
latency, throughput, and estimated cost.

## 35-55 Seconds: Security And Release Gate

Show prompt-injection and PII guardrail tests. Then run:

```bash
python scripts/run_regression_tests.py
python scripts/check_eval_thresholds.py --artifact runs/agenttrust_regression_eval.jsonl
```

Explain that the release gate returns PASS, BLOCK, or ESCALATE from configurable thresholds, so CI
can fail unsafe or unreliable agent changes.

## 55-75 Seconds: Dashboard Evidence

Open `/dashboard` locally. Point to real metrics derived from JSONL artifacts: pass rate, p50/p95
latency, throughput, error rate, cost/request estimate, failure examples, historical run groups,
and downloadable evidence files. State clearly that the public Vercel page is static and the
FastAPI API is currently verified locally.

## 75-90 Seconds: Interview Close

This project demonstrates AI Solutions Engineering, LLM Evaluation Engineering, and Applied GenAI
reliability work: testable evaluator design, security regressions, CI release gates, structured
observability, evidence-backed dashboards, and honest deployment boundaries.
