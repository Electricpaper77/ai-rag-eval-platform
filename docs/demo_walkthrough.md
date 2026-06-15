# Demo Walkthrough

## 30-Second Project Summary

This is a portfolio-grade AI RAG evaluation platform for validating LLM and model responses before deployment. It combines an OpenAI-compatible inference gateway, deterministic RAG and security evaluation, Prometheus metrics, JSONL audit logs, simulated GPU/platform evidence, and checksum-backed summaries.

## Problem This Project Solves

Teams need a repeatable way to prove that GenAI systems are safe, observable, and evaluation-ready before they ship. This project shows how to evaluate hallucination risk, citation behavior, prompt-injection resistance, PII handling, refusal behavior, routing quality, and operational health with artifacts a reviewer can inspect locally.

## Architecture Summary

- FastAPI inference gateway exposes `POST /v1/chat/completions`.
- Evaluation endpoints and guardrail logic score model responses.
- RAG components support citation-aware retrieval workflows.
- Security validators run deterministic red-team checks without calling external models.
- Prometheus metrics expose inference, eval, GPU, and security signals.
- JSONL artifacts record eval runs, routing decisions, benchmark results, and proof outputs.
- Evidence script summarizes eval artifacts and records SHA256 checksums.
- Kubernetes, Helm, Docker, and Cloud Build files show cloud deployment packaging.

## Validation Status

| Check | Result |
|---|---:|
| Focused AgentTrust demo tests | 2 passed |
| Repository collection | 128 tests collected |
| Full legacy/shared fixture suite | Not the official judge validation path |

## Security Eval Layer Summary

The security report documents a historical 31-case deterministic suite. Its referenced source
fixture, validator module, and dedicated tests are not present in this checkout, so it is not part
of the current reproducible judge validation path.

Key artifact: [security_eval_report.md](security_eval_report.md)

## Evidence Integrity Layer Summary

The evidence layer reads checked-in JSONL eval artifacts and writes:

- [eval_summary.json](artifacts/eval_summary.json)
- [eval_summary.md](artifacts/eval_summary.md)

The report separates the 6-prompt guardrail smoke sample from the 125-prompt historical eval benchmark and records SHA256 checksums for each input JSONL artifact.

## Artifact Links

- [Proof index](proof_index.md)
- [Security eval report](security_eval_report.md)
- [Threat model](threat_model.md)
- [Eval evidence summary](artifacts/eval_summary.md)
- [Eval JSONL log](artifacts/eval_runs/eval_runs.jsonl)
- [Historical eval run](artifacts/runs/eval_run_001.jsonl)
- [Metrics sample](artifacts/metrics_sample.txt)
- [Cloud Build config](../cloudbuild.yaml)
- [Kubernetes manifests](../k8s/)

## Commands To Reproduce Results

```bash
python -m pytest tests/test_agenttrust_demo.py -q
python -m pytest --collect-only -q
git diff --check
```

## Resume-Ready Bullets

- Built a FastAPI RAG and LLM evaluation platform with deterministic reliability checks,
  checksum-backed JSONL evidence, Prometheus metrics, OpenAI-compatible inference, and a focused
  reproducible AgentTrust judge-validation path.
- Implemented AI security evaluation coverage for prompt injection, PII redaction, unsafe retrieval, malformed input, jailbreak-style instruction conflicts, and irrelevant-context RAG abuse using deterministic validators and documented threat mapping.
- Added recruiter-verifiable proof artifacts including eval JSONL logs, SHA256 evidence summaries, Prometheus metric samples, GPU benchmark proof logs, and Docker/Kubernetes/Cloud Build configuration.

## Interview Talking Points

- I designed this as a proof-driven GenAI portfolio project: core evaluation claims have tests or inspectable artifacts.
- The security layer is deterministic so CI can catch regressions without relying on flaky model calls.
- The evidence layer makes eval claims reviewable by tying metrics back to SHA256 checksums of source JSONL artifacts.
- The platform demonstrates both customer-facing AI Solutions work and engineering depth: APIs, evaluation, observability, security, routing, and deployment packaging.
