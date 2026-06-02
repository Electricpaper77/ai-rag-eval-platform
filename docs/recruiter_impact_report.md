# Recruiter-Impact Report

## Senior NVIDIA AI Infrastructure Review

Single highest-impact missing infrastructure feature: production OpenTelemetry trace export.

## Why This Feature

The repository already had the other prioritized hiring signals:

- TTFT metrics
- tokens/sec metrics
- backend comparison leaderboard
- Kubernetes deployment manifests

The missing gap was that traces existed only as local OTEL-shaped JSONL artifacts. For NVIDIA, AMD, Databricks, OpenAI, and Anthropic infrastructure roles, a real OTLP export path is a stronger production signal because it shows the candidate can connect gateway requests, routing decisions, and backend calls to a standard observability pipeline.

## Implemented

- Optional OpenTelemetry SDK integration in `app/tracing.py`.
- OTLP HTTP trace export when `OTEL_EXPORTER_OTLP_ENDPOINT` or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is configured.
- OpenTelemetry Collector service in `docker-compose.yml`.
- Collector config in `observability/otel-collector/config.yaml`.
- Kubernetes environment wiring for OTLP export in `k8s/deployment.yaml`.
- Local JSONL fallback preserved for offline tests and portfolio proof.
- Pipeline proof artifact at `docs/artifacts/opentelemetry_pipeline.json`.

## Hiring Signal Raised

Before: trace-like JSONL artifacts showed local request/backend causality.

After: the gateway has a production trace export path compatible with collector-backed observability stacks, while still generating offline proof artifacts for recruiters.

## Validation

- `pytest -q`: `17 passed`
- `docker compose config --quiet`: valid, with a local Docker config permission warning unrelated to the repository config.
- New proof artifacts:
  - `docs/artifacts/opentelemetry_pipeline.json`
  - `docs/artifacts/otel_traces.jsonl`
  - `observability/otel-collector/config.yaml`

