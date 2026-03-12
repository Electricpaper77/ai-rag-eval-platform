# AI RAG Evaluation Platform

Production-style GenAI evaluation infrastructure built to validate LLM releases before deployment.

## Stack
FastAPI • Docker • GCP Cloud Run • Prometheus • JSONL evaluation logs • CI/CD (Cloud Build)

## Capabilities
- automated prompt evaluation harness
- RAG validation pipeline
- batch evaluation runs
- Prometheus runtime telemetry
- latency monitoring (p50/p95)
- load validation testing

## Example Metrics

| Metric | Result |
|------|------|
| prompts evaluated | 120 |
| evaluation pass rate | ~87% |
| latency p50 | ~420ms |
| latency p95 | ~1.2s |
| load validation | 500 requests |
| concurrency tested | 25 |

## Observability

Prometheus metrics exposed via `/metrics`

Artifacts:
screenshots/observability/

## Deployment

Containerized service deployed to Google Cloud Run with CI/CD pipeline using Google Cloud Build.

