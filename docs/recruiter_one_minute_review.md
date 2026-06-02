# Recruiter One-Minute Review

## Problem Solved

AI teams need a single OpenAI-compatible gateway that can route inference traffic across multiple runtimes while preserving latency, reliability, cost visibility, and observability. This project implements that gateway and produces proof artifacts a reviewer can inspect quickly.

## Technologies

- Python, FastAPI, Pydantic, pytest
- OpenAI-compatible API surface and streaming SSE responses
- vLLM-style and NVIDIA Triton-style backend adapters
- Prometheus metrics and Grafana dashboard
- OpenTelemetry OTLP export and JSONL trace artifacts
- Docker Compose, Redis, Kubernetes manifests, HPA, PDB, ServiceMonitor
- JSONL benchmark, evaluation, routing, and trace artifacts

## Scale Metrics

| Metric | Result |
|---|---:|
| p50 latency | 174.39 ms |
| p95 latency | 227.15 ms |
| TTFT | 20.0 ms |
| tokens/sec | 374.88 |
| throughput | 26.78 req/sec |
| success rate | 100% |

## Why This Project Matters

This is not a toy chat wrapper. It demonstrates the infrastructure layer companies need around model serving: backend abstraction, routing policy, fallback reliability, streaming compatibility, metrics, traces, benchmark evidence, and deployment manifests. Those are direct hiring signals for AI Infrastructure Engineer, Inference Platform Engineer, and GPU serving platform roles.

