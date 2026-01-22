# AI RAG Evaluation Platform

A production-style Retrieval-Augmented Generation (RAG) evaluation backend built with FastAPI and ChromaDB.  
Designed to ingest documents, perform vector search, and log retrieval performance metrics for LLM evaluation.

## ✅ Evaluation Demo (Working)

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
- Refund policy → `refund_policy.md`
- Shipping time → `shipping_policy.md`
- Support hours → `shipping_policy.md`

The first run downloads the embedding model; subsequent runs execute in milliseconds.

## Metrics (Automated)

Run an evaluation batch and return aggregate retrieval metrics:

- Hit Rate (questions with ≥1 citation): **100%** (3/3)
- Avg Latency: **~298 ms**
- Total Questions: **3**

### Reproduce locally (Docker running on :8000)

```powershell
curl.exe -s -X POST "http://127.0.0.1:8000/eval/run" -H "accept: application/json" | Tee-Object results\latest_eval.json
type results\latest_eval.json


## Features

* 📄 Document ingestion with chunking
* 🔍 Vector search using ChromaDB (cosine similarity)
* 📌 Source-aware citations per query
* ⏱️ Latency + retrieval metrics logging
* 📊 CSV-based evaluation output for offline analysis

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



