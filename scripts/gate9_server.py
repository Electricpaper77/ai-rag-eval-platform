"""Real AgentTrust HTTP serving process used by Gate 9 capacity validation."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time

from fastapi import FastAPI, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import JSONResponse, Response

import backend.app.capacity as capacity_module
from backend.app.capacity import (
    CapacityController,
    CapacityExhausted,
    CapacityTimeout,
    router as capacity_router,
)
from backend.app.inference import handle_chat_completions_async


CPU_WORK_MS = max(0, min(2000, int(os.getenv("GATE9_CPU_WORK_MS", "0"))))
VERSION = os.getenv("GATE9_VERSION", "capacity")
controller = CapacityController(
    capacity_per_replica=int(os.getenv("GATE9_MAX_INFLIGHT_PER_REPLICA", "4")),
    queue_capacity=int(os.getenv("GATE9_QUEUE_CAPACITY", "8")),
)
capacity_module.DEFAULT_CONTROLLER = controller
app = FastAPI(title="AgentTrust Gate 9 capacity runtime")
app.include_router(capacity_router)


def _cpu_work(milliseconds: int) -> None:
    if not milliseconds:
        return
    deadline = time.perf_counter() + milliseconds / 1000.0
    value = 0
    while time.perf_counter() < deadline:
        value = (value * 33 + 17) % 1000003
    hashlib.sha256(str(value).encode()).digest()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": VERSION}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ready", "version": VERSION}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/chat/completions", response_model=None)
async def chat(request: dict[str, object]) -> dict[str, object] | Response:
    try:
        await controller.acquire(timeout_seconds=float(os.getenv("GATE9_QUEUE_TIMEOUT_SECONDS", "1.5")))
    except CapacityExhausted:
        return JSONResponse({"error": {"reason_code": "capacity_exhausted", "message": "capacity exhausted"}}, status_code=503)
    except CapacityTimeout:
        return JSONResponse({"error": {"reason_code": "capacity_queue_timeout", "message": "capacity queue timeout"}}, status_code=429)
    try:
        # Keep the event loop responsive while the disposable load test burns CPU.
        # This lets Kubernetes probes and the HPA observe a stable serving pod.
        await asyncio.to_thread(_cpu_work, CPU_WORK_MS)
        payload = await handle_chat_completions_async(request)
        payload["capacity"] = controller.snapshot().__dict__
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await controller.release()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
