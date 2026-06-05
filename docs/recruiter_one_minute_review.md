# Recruiter One-Minute Review

## What It Solves

RAG and LLM applications need repeatable checks for unsupported answers, missing citations, unsafe responses, prompt injection, and behavior drift. This project provides a FastAPI evaluation path, auditable JSONL evidence, Prometheus-format metrics, and pytest regression coverage.

## Strongest Hiring Signals

- Deterministic citation, hallucination, refusal, PII, and prompt-injection evaluation.
- OpenAI-compatible inference and streaming interfaces.
- Checksum-backed evidence across 131 fixture records.
- JSONL logs, metrics, traces, and local load-test artifacts.
- Docker, Kubernetes, Helm, and Terraform packaging without claiming a live production cluster.

## Evidence Snapshot

| Evidence | Result |
|---|---:|
| Controlled hiring smoke run | 6 / 6 passed |
| Combined fixture evidence | 127 / 131 passed |
| Combined hallucination rate | 0.8% |
| Combined citation precision | 83.3% |
| Combined refusal accuracy | 83.3% |
| Current local pytest result | 133 passed, 1 expected xfail |

## Operational Artifact

The checked-in local load test contains 290 requests at 10 virtual users:

| Metric | Result |
|---|---:|
| Successful checks | 284 / 290 |
| Request rate | 9.39 req/sec |
| HTTP failure rate | 2.07% |
| p95 successful-response latency | 53.44 ms |

These numbers are local artifact results, not production capacity claims.

## Role Fit

The strongest alignment is AI Solutions Engineer, LLM Evaluation Engineer, Applied GenAI Engineer, and AI Reliability Engineer. Infrastructure components provide useful supporting depth, while GPU execution and production cluster operation are explicitly outside the demonstrated scope.
