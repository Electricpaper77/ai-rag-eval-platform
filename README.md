![smoke](../../actions/workflows/smoke.yml/badge.svg)

CI runs a smoke test on every push (starts the FastAPI API + runs scripts/smoke.ps1).


# AI RAG Evaluation Platform

A production-style Retrieval-Augmented Generation (RAG) evaluation backend built with FastAPI and ChromaDB.  
Designed to ingest documents, perform vector search, and log retrieval performance metrics for LLM evaluation.

## âœ… Evaluation Demo (Working)

This project includes a minimal RAG evaluation endpoint.

**Endpoint**
POST `/eval/run`

**What it does**
- Runs a fixed set of evaluation questions
- Queries ChromaDB (cosine similarity)
- Returns:
  - latency_ms
  - num_citations
  - top_source

**Example Output**
- Refund policy â†’ `refund_policy.md`
- Shipping time â†’ `shipping_policy.md`
- Support hours â†’ `shipping_policy.md`

The first run downloads the embedding model; subsequent runs execute in milliseconds.

## Live Demo (Cloud Run)
- Swagger UI: https://rag-eval-api-t7a5wdzsna-uc.a.run.app/docs
- Health: https://rag-eval-api-t7a5wdzsna-uc.a.run.app/health
- `Public Cloud Run deployment (FastAPI).`

### Demo (Cloud Run)

Public Cloud Run deployment (FastAPI).

```powershell
curl.exe https://rag-eval-api-t7a5wdzsna-uc.a.run.app/health
start https://rag-eval-api-t7a5wdzsna-uc.a.run.app/docs


# AI RAG Evaluation Platform
FastAPI + ChromaDB RAG service with automated evaluation (hit rate + latency) and citation logging.

## Tech Stack
- FastAPI, Uvicorn
- ChromaDB (vector store), sentence-transformers embeddings
- Docker

## Quickstart (Docker)
docker build -t rag-eval-platform .
docker run -d --name rag-eval -p 8000:8000 rag-eval-platform

## Demo
# 1) Ingest sample docs
curl.exe -X POST "http://127.0.0.1:8000/ingest" -H "content-type: application/json" -d "{ \"path\": \"data/sample_docs\" }"

# 2) Query
curl.exe -X POST "http://127.0.0.1:8000/query" -H "content-type: application/json" -d "{ \"question\": \"What is the refund policy?\", \"top_k\": 4 }"

# 3) Run eval
curl.exe -s -X POST "http://127.0.0.1:8000/eval/run" -H "accept: application/json"


## Metrics (Automated)

Run an evaluation batch and return aggregate retrieval metrics:

- Hit Rate (questions with â‰¥1 citation): **100%** (3/3)
- Avg Latency: **~298 ms**
- Total Questions: **3**

### Reproduce locally (Docker running on :8000)

```powershell
curl.exe -s -X POST "http://127.0.0.1:8000/eval/run" -H "accept: application/json" | Tee-Object results\latest_eval.json
type results\latest_eval.json

### Latest Eval (sample)

- Hit Rate (â‰¥1 citation): **100%** (3/3)
- Avg Latency: **~298 ms**
- Total Questions: **3**

Sample (truncated):
```json
{
  "stats": { "hit_rate_pct": 100.0, "avg_latency_ms": 297.7, "total_questions": 3 },
  "results": [
    { "question": "What is the refund policy?", "num_citations": 3, "top_source": "data/sample_docs/refund_policy.md" },
    { "question": "How long does shipping take?", "num_citations": 3, "top_source": "data/sample_docs/shipping_policy.md" },
    { "question": "What are the support hours?", "num_citations": 3, "top_source": "data/sample_docs/shipping_policy.md" }
  ]
}


## Features

* ðŸ“„ Document ingestion with chunking
* ðŸ” Vector search using ChromaDB (cosine similarity)
* ðŸ“Œ Source-aware citations per query
* â±ï¸ Latency + retrieval metrics logging
* ðŸ“Š CSV-based evaluation output for offline analysis

## Architecture

\## Evaluation \& Monitoring



The platform includes a lightweight evaluation harness for regression testing and performance monitoring.



\### Run Evaluation

`POST /eval/run`



This endpoint executes a fixed set of evaluation questions against the RAG pipeline and logs metrics to a CSV file.



\*\*Metrics logged (`results/evals.csv`):\*\*

\- timestamp

\- question

\- top\_k

\- answer\_length

\- num\_citations

\- latency\_ms



This enables basic regression testing and latency tracking as prompts, embeddings, or retrieval logic change.



## RAG Evaluation Harness

FastAPI-based RAG backend with a deterministic evaluation harness.

### Features
- ChromaDB vector store (persistent)
- Source-grounded answers with file-level citations
- Deterministic eval sets (JSON)
- Metrics: citation hit-rate, average latency, citation count

### Run locally
uvicorn backend.app.main:app --reload

### Ingest documents (PowerShell)
$body = @{ path = "data\sample_docs" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/ingest" -ContentType "application/json" -Body $body

### Query (PowerShell)
$body = @{ question = "What is the refund policy?"; top_k = 4 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/query" -ContentType "application/json" -Body $body

### Run evaluation
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/eval/run"

### Example Metrics
- Hit rate: 100%
- Avg latency: ~330ms
- Citations per answer: 4

## Smoke Test (30s)

```powershell
$env:BASE="http://127.0.0.1:8002"
powershell -ExecutionPolicy Bypass -File .\scripts\smoke.ps1
```

Expected output: `/docs reachable`, metrics table, `smoke passed`.



