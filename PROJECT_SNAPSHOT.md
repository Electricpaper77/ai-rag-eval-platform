# AI RAG Evaluation Platform — Snapshot

## Overview
Production-style GenAI evaluation and validation platform designed to test LLM inference systems for reliability, performance, and correctness.

Core capabilities include:

- automated regression evaluation
- inference benchmarking
- latency and throughput measurement
- CI/CD evaluation validation
- artifact persistence for reproducible benchmarks

---

## System Architecture

Client
  ↓
FastAPI Evaluation API (/evaluate)
  ↓
Prompt Processing
  ↓
LLM Inference
  ↓
Evaluation Metrics
  ↓
Artifacts + Logs

Supporting systems:

- Benchmark runner
- Regression test suite
- GitHub Actions evaluation pipeline

---

## Performance Metrics

Example benchmark results:

| prompts | p50 latency | p95 latency | throughput |
|-------|-------------|-------------|-----------|
| 10 | ~3.1 ms | ~5.0 ms | ~308 rps |
| 200 | ~3.9 ms | ~5.1 ms | ~261 rps |

Artifacts stored in:

benchmarks/
benchmark_*.json

---

## Validation Pipeline

Automated validation executed through:

scripts/run_regression_tests.py

CI/CD pipeline runs:

1. regression evaluation
2. benchmark validation

Pipeline located in:

.github/workflows/evaluation_pipeline.yml

---

## Key Features

- LLM evaluation harness
- automated performance benchmarking
- regression validation suite
- CI/CD evaluation gating
- artifact persistence

