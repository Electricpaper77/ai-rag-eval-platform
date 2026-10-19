"""Real AgentTrust serving process for Gate 10 disposable resilience experiments."""

from __future__ import annotations

import asyncio
import os
import time
import urllib.request

from fastapi import FastAPI, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import JSONResponse, Response

import backend.app.capacity as capacity_module
from backend.app.capacity import CapacityController, CapacityExhausted, CapacityTimeout, router as capacity_router
from backend.app.inference import handle_chat_completions_async
from backend.app.metrics import HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION_SECONDS
from backend.app.resilience.controller import (
    DEFAULT_CONTROLLER as resilience_controller,
    DEPENDENCY_FAILURES_TOTAL,
    router as resilience_router,
)


GATE10_LATENCY_MS = min(3000, max(0, int(os.getenv("GATE10_FORCE_LATENCY_MS", "0"))))
GATE10_ERROR_RATE = min(1.0, max(0.0, float(os.getenv("GATE10_FORCE_ERROR_RATE", "0"))))
DEPENDENCY_URL = os.getenv("GATE10_DEPENDENCY_URL", "http://gate10-dependency:8081/healthz")
VERSION = os.getenv("GATE10_VERSION", "resilience")
controller = CapacityController(
    capacity_per_replica=int(os.getenv("GATE9_MAX_INFLIGHT_PER_REPLICA", "4")),
    queue_capacity=int(os.getenv("GATE9_QUEUE_CAPACITY", "8")),
)
capacity_module.DEFAULT_CONTROLLER = controller

RESILIENCE_REQUESTS_TOTAL = Counter("agenttrust_resilience_requests_total", "Resilience request outcomes", ["result"])
RESILIENCE_LATENCY_SECONDS = Histogram("agenttrust_resilience_request_latency_seconds", "Resilience request latency")
RESILIENCE_FAULT_ACTIVE = Gauge("agenttrust_resilience_fault_active", "Whether a Gate 10 fault is active")

app = FastAPI(title="AgentTrust Gate 10 resilience runtime")
app.include_router(capacity_router)
app.include_router(resilience_router)


async def _dependency_check() -> None:
    if resilience_controller.is_active("dependency_unavailable") or resilience_controller.is_active("network_denial"):
        DEPENDENCY_FAILURES_TOTAL.inc()
        raise OSError("dependency fault is active")
    try:
        await asyncio.to_thread(urllib.request.urlopen, DEPENDENCY_URL, timeout=1.0)
    except Exception as exc:
        DEPENDENCY_FAILURES_TOTAL.inc()
        raise OSError("dependency unavailable") from exc


def _record_request(status: int, started: float) -> None:
    duration = max(0.0, time.perf_counter() - started)
    HTTP_REQUESTS_TOTAL.labels("POST", "/v1/chat/completions", str(status)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels("POST", "/v1/chat/completions").observe(duration)
    RESILIENCE_REQUESTS_TOTAL.labels("success" if 200 <= status < 300 else "failure").inc()
    RESILIENCE_LATENCY_SECONDS.observe(duration)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": VERSION}


@app.get("/readyz", response_model=None)
def readyz() -> dict[str, str] | Response:
    RESILIENCE_FAULT_ACTIVE.set(1 if resilience_controller.is_active("readiness_failure") else 0)
    if resilience_controller.is_active("readiness_failure"):
        return JSONResponse({"status": "not_ready", "reason_code": "readiness_failure"}, status_code=503)
    return {"status": "ready", "version": VERSION}


@app.get("/metrics")
def metrics() -> Response:
    RESILIENCE_FAULT_ACTIVE.set(1 if resilience_controller.status()["active"] else 0)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/chat/completions", response_model=None)
async def chat(request: dict[str, object]) -> dict[str, object] | Response:
    started = time.perf_counter()
    status = 500
    acquired = False
    try:
        try:
            await controller.acquire(timeout_seconds=float(os.getenv("GATE9_QUEUE_TIMEOUT_SECONDS", "1.5")))
            acquired = True
        except CapacityExhausted:
            status = 503
            return JSONResponse({"error": {"reason_code": "capacity_exhausted", "message": "capacity exhausted"}}, status_code=status)
        except CapacityTimeout:
            status = 429
            return JSONResponse({"error": {"reason_code": "capacity_queue_timeout", "message": "capacity queue timeout"}}, status_code=status)

        if resilience_controller.is_active("http_5xx") or GATE10_ERROR_RATE >= 1.0:
            status = 500
            return JSONResponse({"error": {"reason_code": "resilience_http_5xx", "message": "controlled Gate 10 fault"}}, status_code=status)
        if resilience_controller.is_active("latency"):
            await asyncio.sleep(min(3.0, float(os.getenv("GATE10_LATENCY_MS", "1200")) / 1000.0))
        elif GATE10_LATENCY_MS:
            await asyncio.sleep(GATE10_LATENCY_MS / 1000.0)
        try:
            await _dependency_check()
        except OSError:
            status = 503
            return JSONResponse({"error": {"reason_code": "dependency_unavailable", "message": "dependency unavailable"}}, status_code=status)
        payload = await handle_chat_completions_async(request)
        payload["resilience"] = {"status": "healthy", "fault": resilience_controller.status()["active"]}
        status = 200
        return payload
    except ValueError as exc:
        status = 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    finally:
        if acquired:
            await controller.release()
        _record_request(status, started)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
