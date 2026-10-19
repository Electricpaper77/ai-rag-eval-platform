"""CPU-safe HTTP model server used by Gate 8 canary validation."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections import Counter

from fastapi import FastAPI, HTTPException

from backend.app.inference import handle_chat_completions_async


VERSION = os.getenv("GATE8_MODEL_VERSION", "baseline")
RUNTIME = os.getenv("GATE8_RUNTIME", "mock")
FORCE_LATENCY_MS = float(os.getenv("GATE8_FORCE_LATENCY_MS", "0") or 0)
FORCE_ERROR_RATE = float(os.getenv("GATE8_FORCE_ERROR_RATE", "0") or 0)
REQUESTS = Counter()

app = FastAPI(title=f"AgentTrust Gate 8 {VERSION} serving runtime")


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {"status": "ok", "version": VERSION, "runtime": RUNTIME}


@app.get("/readyz")
def readyz() -> dict[str, object]:
    return {"status": "ready", "version": VERSION, "runtime": RUNTIME}


@app.get("/v1/models")
def models() -> dict[str, object]:
    return {"data": [{"id": "mock-llm", "version": VERSION, "runtime": RUNTIME}]}


@app.get("/metrics")
def metrics() -> dict[str, object]:
    return {"version": VERSION, "runtime": RUNTIME, "requests": dict(REQUESTS)}


@app.post("/v1/chat/completions")
async def chat(request: dict[str, object]) -> dict[str, object]:
    request_id = str(request.get("request_id") or request.get("x_request_id") or "gate8-unknown")
    REQUESTS["total"] += 1
    if FORCE_ERROR_RATE > 0:
        bucket = int(hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:8], 16) % 10000
        if bucket < int(FORCE_ERROR_RATE * 10000):
            REQUESTS["error"] += 1
            raise HTTPException(status_code=503, detail=f"deterministic {VERSION} defect")
    if FORCE_LATENCY_MS > 0:
        await asyncio.sleep(FORCE_LATENCY_MS / 1000.0)
    started = time.perf_counter()
    payload = await handle_chat_completions_async(request)
    payload["request_id"] = request_id
    payload["serving_runtime"] = RUNTIME
    payload["model_version"] = VERSION
    payload["serving_latency_ms"] = round((time.perf_counter() - started) * 1000.0 + FORCE_LATENCY_MS, 3)
    REQUESTS["success"] += 1
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
