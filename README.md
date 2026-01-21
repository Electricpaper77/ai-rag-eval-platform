# AI RAG Evaluation Platform

A production-style Retrieval-Augmented Generation (RAG) evaluation backend built with FastAPI and ChromaDB.  
Designed to ingest documents, perform vector search, and log retrieval performance metrics for LLM evaluation.

## Features
- 📄 Document ingestion with chunking
- 🔍 Vector search using ChromaDB (cosine similarity)
- 📌 Source-aware citations per query
- ⏱️ Latency + retrieval metrics logging
- 📊 CSV-based evaluation output for offline analysis

## Architecture
