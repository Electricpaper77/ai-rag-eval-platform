# AI RAG Evaluation & Guardrails Platform

## Problem
Modern LLM applications fail silently when retrieval quality degrades or when unsafe inputs (e.g., prompt injection) reach the model. Teams need evaluation, observability, and safety controls before deploying RAG systems to production.

This project demonstrates a production-style RAG evaluation backend with automated metrics and guardrails.

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

## Inference Cost Monitoring
To monitor production inference spend, this repository includes a cost analysis utility that estimates:
- **cost per request**
- **cost per 1000 requests**
- **cost per evaluation (regression) run**

The script uses average token volume and model pricing to estimate expected spend before large regression runs.

Run the analyzer:
```bash
python scripts/cost_analysis.py \
  --avg_tokens_per_request 850 \
  --price_per_1k_tokens 0.002 \
  --requests_per_eval_run 30
```

This writes structured output to:
- `docs/artifacts/cost_analysis.json`

Example output:
```json
{
  "avg_tokens_per_request": 850,
  "price_per_1k_tokens": 0.002,
  "requests_per_eval_run": 30,
  "cost_per_request": 0.0017,
  "cost_per_1000_requests": 1.7,
  "cost_per_eval_run": 0.051
}
```

Use this artifact in CI/CD evaluation jobs to track cost drift as prompt size, retrieval context, or model pricing changes over time.
