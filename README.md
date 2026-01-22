# AI RAG Evaluation Platform

A production-style Retrieval-Augmented Generation (RAG) evaluation backend built with FastAPI and ChromaDB.  
Designed to ingest documents, perform vector search, and log retrieval performance metrics for LLM evaluation.

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



