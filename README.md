# AI RAG Evaluation & Guardrails Platform

## Problem
Modern LLM applications fail silently when retrieval quality degrades or when unsafe inputs (e.g., prompt injection) reach the model.
Teams need evaluation, observability, and safety controls before deploying RAG systems to production.

This project demonstrates a production-style RAG evaluation backend with automated metrics and guardrails.

---

## Architecture
FastAPI-based evaluation service with retrieval, metrics, and safety enforcement.

Core components:
- FastAPI REST API (/query, /query_guarded, /eval/run)
- Vector-based retrieval (ChromaDB)
- Evaluation harness (citation hit-rate, latency)
- Guardrails layer (prompt-injection blocking)
- Automated smoke tests (PowerShell)

Flow:
Request → Guardrails → Retrieval → Evaluation → JSON Response

---

## Evaluation & Metrics
The platform supports automated evaluation runs to measure RAG quality.

Eval endpoint:
- POST /eval/run

Reported metrics:
- Citation hit-rate
- Average latency
- Structured JSON results for analysis

---

## Guardrails (Prompt Injection Blocking)
A guarded query endpoint blocks unsafe inputs before retrieval or generation.

- Endpoint: POST /query_guarded
- Behavior: detects prompt-injection attempts and returns a structured deny response

Example blocked response:
{ "status": "blocked", "reason": "prompt_injection" }

---

## Run Locally

Start the API:
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

Run guardrails smoke test:
powershell -ExecutionPolicy Bypass -File scripts/guardrails.ps1

Expected output:
{ "status": "blocked", "reason": "prompt_injection" }

---

## Why This Matters
This project demonstrates production-style RAG evaluation, safety-first API design, deterministic guardrails behavior,
and automated validation for LLM systems.

---

## Status
Project complete.

## Metrics (Cloud Run)
- Health check latency (n=30): p50 124ms, p95 249ms
- Deployment: Cloud Run (us-central1)
- Live API: https://rag-eval-api-69725201265.us-central1.run.app


## Live Demo Proof (Cloud Run)

**Base URL:** https://rag-eval-api-t7a5wdzsna-uc.a.run.app

### PowerShell Smoke Test (copy/paste)
`powershell
$BASE="https://rag-eval-api-t7a5wdzsna-uc.a.run.app"

# Health
Invoke-RestMethod "$BASE/health"

# Ingest from GCS
$body = @{ path="gs://rag-eval-docs-124909/sample_docs" } | ConvertTo-Json
Invoke-RestMethod -Method POST -Uri "$BASE/ingest" -ContentType "application/json" -Body $body -TimeoutSec 180

# Query (default top_k = 3)
$q = @{ question="Summarize the refund policy with citations." } | ConvertTo-Json
$r = Invoke-RestMethod -Method POST -Uri "$BASE/query" -ContentType "application/json" -Body $q -TimeoutSec 60
$r.status
$r.num_citations
$r.citations.source
$r.latency_ms


## Quickstart (Run Regression Eval)

### Local
`powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --port 8000

## Proof: Regression Eval Output (JSONL)

Real eval record produced by POST /eval/regression (truncated):

`json
{"run_id": "67414973d53f49b5a5a0c343df5e1031", "variant": "base", "question_id": "refund_1", "question": "What is the refund policy?", "prompted_question": "What is the refund policy?", "answer": "# Refund Policy\nCustomers can request a refund within 30 days of delivery.\nRefunds are issued to the original payment met ...
