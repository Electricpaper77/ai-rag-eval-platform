# Interview Talk Track

## 60-Second Explanation

This project is a portfolio-grade AI RAG evaluation platform. It exposes an OpenAI-compatible inference endpoint, evaluates model responses for hallucination risk, citation coverage, refusal behavior, PII leakage, and prompt-injection compliance, and records evidence as JSONL logs and Prometheus metrics. The historical security report documents 31 cases, while the checksum-backed evidence report summarizes 131 fixture records. Current validation reports 2 focused AgentTrust demo tests passing, 128 tests collected, and a non-green full suite with 99 passed, 28 failed, and 1 expected xfail.

## Technical Deep-Dive Answers

**How is the platform structured?**  
The core service is FastAPI. It has an OpenAI-compatible `/v1/chat/completions` surface, evaluation logic, RAG citation checks, metrics, routing, GPU/platform proof paths, and deployment packaging. The important design choice is that evaluation and proof artifacts are first-class outputs rather than hidden logs.

**How do you avoid flaky LLM eval tests?**  
The current AgentTrust demo validation is deterministic and requires no external model call. The historical security report also documents a deterministic red-team dataset and validator design, but those original source files are not present in this checkout.

**How does the evidence layer work?**  
The checked-in `docs/artifacts/eval_summary.json` and `docs/artifacts/eval_summary.md` record pass rate, hallucination rate, citation precision, refusal/guardrail accuracy, prompt counts, timestamps, and SHA256 checksums. They are preserved evidence artifacts; the original generation script is not present in this checkout.

## Business / Customer-Facing Answers

**What customer problem does this solve?**  
It helps teams answer: "Can we trust this GenAI workflow enough to deploy it?" The platform gives evaluators and stakeholders concrete proof of safety checks, reliability metrics, and evidence artifacts.

**How would you demo this to a non-engineering stakeholder?**  
I would start with the README fast path, show the validation status, open the security eval report, open the evidence summary, and then show one JSONL eval log so they can see that the metrics come from inspectable records.

**Why does this matter for AI Solutions Engineering?**  
Solutions Engineers often need to bridge technical depth and customer trust. This repo shows how to explain architecture, run validation, map security controls to risks, and package proof in a format a customer or hiring manager can inspect quickly.

## Security / Evaluation Answers

**What security cases are covered?**  
The historical 31-case report covers prompt injection, jailbreak-style instruction conflicts, PII leakage, unsafe retrieval, malformed input, and irrelevant-context RAG abuse. Its original fixture and dedicated tests are not present in this checkout.

**How do you evaluate hallucination and citation behavior?**  
The reliability evaluator scores hallucination risk and citation coverage, records failure reasons, and persists the results to JSONL. The evidence summary then aggregates documented eval artifacts and separates smoke validation from historical benchmark evidence.

**How do you prove the metrics are tied to the underlying data?**  
The checked-in evidence summary records SHA256 checksums for each input artifact so a reviewer can compare the documented metrics with the referenced JSONL files. The original regeneration script is not included in this checkout.

## Metrics-Focused Answers

**What validation metrics should I quote?**  
Quote 2 passing focused AgentTrust demo tests and 128 collected tests. If discussing the full suite, state the complete current result: 99 passed, 28 failed, and 1 expected xfail. For evidence artifacts, quote 131 documented eval prompts aggregated across the smoke sample and historical benchmark.

**What operational metrics are exposed?**  
The platform exposes Prometheus-format metrics for inference latency, TTFT, tokens/sec, routing decisions, eval pass/fail counts, category failures, GPU serving signals, and AI security gauges.

**What proof artifacts show engineering readiness?**
Use `docs/artifacts/eval_summary.md`, `docs/security_eval_report.md`,
`docs/artifacts/metrics_sample.txt`, `docs/artifacts/gpu_observability_runs.jsonl`,
`tests/test_canary_policy.py`, `cloudbuild.yaml`, and the `k8s/` manifests. These demonstrate
implementation and packaging, not a live production cluster. The security report is historical
documentation; its original fixture and dedicated tests are not present in this checkout.
