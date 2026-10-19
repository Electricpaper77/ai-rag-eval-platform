"""HTTP inference worker for the Gate 7 distributed topology."""

from __future__ import annotations

import asyncio
import os
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from backend.app.inference import handle_chat_completions_async


WORKER_ID = os.getenv("GATE7_WORKER_ID", socket.gethostname())
MAX_INFLIGHT = max(1, int(os.getenv("GATE7_WORKER_MAX_INFLIGHT", "8")))
_semaphore = asyncio.Semaphore(MAX_INFLIGHT)
_active = 0
_total = 0
_failed = 0


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="AgentTrust Gate 7 inference worker", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "worker_id": WORKER_ID,
        "hostname": socket.gethostname(),
        "active_requests": _active,
        "total_requests": _total,
        "failed_requests": _failed,
        "accelerator_type": "cpu",
        "accelerator_count": 0,
    }


@app.get("/readyz")
async def readyz() -> dict:
    return {"status": "ready", "worker_id": WORKER_ID}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/chat/completions")
async def chat_completions(payload: dict, request: Request) -> JSONResponse:
    global _active, _total, _failed
    request_id = request.headers.get("x-request-id", "")
    if _semaphore.locked():
        return JSONResponse(status_code=503, content={"error": {"reason_code": "worker_saturated"}})
    async with _semaphore:
        _active += 1
        _total += 1
        try:
            body = await handle_chat_completions_async(payload)
            body["worker_id"] = WORKER_ID
            response = JSONResponse(content=body)
            response.headers["x-agenttrust-worker-id"] = WORKER_ID
            if request_id:
                response.headers["x-request-id"] = request_id
            return response
        except Exception:
            _failed += 1
            raise
        finally:
            _active = max(0, _active - 1)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
