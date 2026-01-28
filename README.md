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
