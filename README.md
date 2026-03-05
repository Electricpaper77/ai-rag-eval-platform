<<<<<<< HEAD
![Eval Gate](https://github.com/Electricpaper77/ai-rag-eval-platform/actions/workflows/eval-gate.yml/badge.svg)
﻿## Whatnot-style Marketplace Analytics & Experimentation
- SQL cohort analysis
- A/B testing framework
- Metric-driven decision dashboards
=======
>>>>>>> origin/project3-infra-observability
# AI RAG Evaluation & Guardrails Platform

## Problem
Modern LLM applications fail silently when retrieval quality degrades or when unsafe inputs (e.g., prompt injection) reach the model. Teams need evaluation, observability, and safety controls before deploying RAG systems to production.

This project demonstrates a production-style RAG evaluation backend with automated metrics and guardrails.

<<<<<<< HEAD
---
## Production Hardening (Cloud Run)
- Containerized FastAPI service with Docker + gunicorn (UvicornWorker) and correct Cloud Run PORT binding (0.0.0.0:$PORT).
- Cloud Run autoscaling controls: minScale=1, maxScale=2, CPU boost enabled.
- Debug artifacts captured during rollout: `proof/project3/cloudrun_debug_snapshot.txt`.

## CI Eval Gate (GitHub Actions)
- PR checks start the FastAPI backend, wait for `/health`, run `scripts/ci_eval.py`, and upload artifacts:
  - `runs/ci_metrics.json` (metrics output)
  - `runs/uvicorn.log` (server log for debugging)

## Proof & Demos (Recruiter Quick-Scan)
- **CI Eval Gate:** PR checks start backend, wait for `/health`, run `scripts/ci_eval.py`, and upload artifacts (`runs/ci_metrics.json`, `runs/uvicorn.log`).
- **Cloud Run Hardening Proof:** `proof/project3/cloudrun_debug_snapshot.txt`
- **Key signals:** Docker + gunicorn ($PORT binding), CI gating, metrics artifacts, structured logs.

=======
>>>>>>> origin/project3-infra-observability
## Architecture
FastAPI-based evaluation service with retrieval, metrics, and safety enforcement.

Core components:
- FastAPI REST API (`/query`, `/query_guarded`, `/eval/run`)
- Vector-based retrieval (ChromaDB)
- Evaluation harness (citation hit-rate, latency)
- Guardrails layer (prompt-injection blocking)
- Prometheus metrics endpoint (`/metrics`)

Flow:
Request → Guardrails → Retrieval → Evaluation → JSON Response

<<<<<<< HEAD
---

## Evaluation & Metrics
The platform supports automated evaluation runs to measure RAG quality.

Eval endpoint:
- POST /eval/run

Reported metrics:
- Citation hit-rate
- Average latency
- Structured JSON results for analysis
- **Eval pass rate:** 100% (N=10)
- **Latency:** p95 522 ms

---

## Guardrails (Prompt Injection Blocking)
A guarded query endpoint blocks unsafe inputs before retrieval or generation.

- Endpoint: POST /query_guarded
- Behavior: detects prompt-injection attempts and returns a structured deny response

Example blocked response:
{ "status": "blocked", "reason": "prompt_injection" }

---

=======
>>>>>>> origin/project3-infra-observability
## Run Locally
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Guardrails smoke test:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/guardrails.ps1
```

## Dependency Pinning Verification
Pinned dependencies are maintained for deterministic builds:
- `chromadb==0.4.24`
- `numpy==1.26.4`

Both root and backend requirements files are aligned to the same pinned ChromaDB version.

## Cloud Run Deploy Instructions
```bash
PROJECT_ID="<gcp-project-id>"
REGION="us-central1"
REPO="rag-eval-repo"
IMAGE="api"
SERVICE="ai-rag-eval"

# Build and push container

gcloud builds submit \
  --config cloudbuild.yaml \
  --project "$PROJECT_ID"

# Deploy latest image to Cloud Run

gcloud run deploy "$SERVICE" \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$IMAGE:ci-test" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080
```

Post-deploy verification:
```bash
BASE_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
curl -sS "$BASE_URL/health"
curl -sS "$BASE_URL/metrics" | head -n 20
```

## Proof Artifacts
- [Load Test Summary JSON](docs/artifacts/load_test_results.json)
- [Raw Load Test Runs](docs/artifacts/runs/)
- [Prometheus Metrics Sample](docs/artifacts/metrics_sample.txt)
- [Observability Notes](docs/artifacts/observability.md)

## Observability (Prometheus Metrics)

The AI RAG Evaluation Platform exposes runtime metrics for infrastructure monitoring.

Endpoint:
https://ai-rag-eval-69725201265.us-central1.run.app/metrics

Example metrics exported:
- process_cpu_seconds_total
- process_virtual_memory_bytes
- process_resident_memory_bytes
- python_gc_collections_total
- process_open_fds

Proof Artifact:
docs/artifacts/metrics_live_sample.txt

These metrics allow monitoring of service health, CPU usage, memory usage, and runtime behavior for the deployed Cloud Run service.


## Cost / Request (Ops)

Cost is tracked using Cloud Billing + request volume. Cost/request is computed as:

cost_per_request_usd = total_cost_usd / total_requests

Artifact:
docs/artifacts/cost_per_request.md

Notes:
- Cloud Run costs vary with CPU/memory allocation, concurrency, and cold starts.
- Use this metric to compare configs (min instances, concurrency) and keep budgets stable.
