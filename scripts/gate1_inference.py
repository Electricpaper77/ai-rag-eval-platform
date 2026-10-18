"""Minimal AgentTrust IQ inference service for the Gate 1 runtime workload."""

import asyncio
import logging
import os
import time

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from backend.app.inference import handle_chat_completions_async
from backend.app.metrics import (
    HEALTHZ_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_FLIGHT,
    HTTP_REQUESTS_TOTAL,
    INFERENCE_ERRORS_TOTAL,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("agenttrust.gate5")

app = FastAPI(title="AgentTrust IQ Gate 1 inference")


def gate5_force_errors_enabled() -> bool:
    return os.getenv("GATE5_FORCE_ERRORS", "").strip().lower() in {"1", "true", "yes"}


def gate5_force_latency_ms() -> float:
    return float(os.getenv("GATE5_FORCE_LATENCY_MS", "0") or "0")


@app.middleware("http")
async def observe_http(request, call_next):
    started = time.perf_counter()
    status = "500"
    HTTP_REQUESTS_IN_FLIGHT.inc()
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        path = request.url.path
        HTTP_REQUESTS_TOTAL.labels(method=request.method, path=path, status=status).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, path=path).observe(
            max(time.perf_counter() - started, 0.0)
        )
        HTTP_REQUESTS_IN_FLIGHT.dec()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    HEALTHZ_REQUESTS_TOTAL.labels(status="200").inc()
    logger.info("healthz status=200")
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "agenttrust-iq", "status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/chat/completions")
async def chat_completions(payload: dict) -> dict:
    forced_error = gate5_force_errors_enabled()
    forced_latency_ms = gate5_force_latency_ms()
    logger.info(
        "chat request model=%s forced_error=%s forced_latency_ms=%s",
        payload.get("model", "mock-llm"),
        forced_error,
        forced_latency_ms,
    )
    if forced_latency_ms > 0:
        await asyncio.sleep(forced_latency_ms / 1000.0)
    if forced_error:
        INFERENCE_ERRORS_TOTAL.labels(reason="gate5_forced_error").inc()
        logger.warning("chat request forced_error=true status=500")
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Gate 5 forced error")
    try:
        response = await handle_chat_completions_async(payload)
        logger.info("chat response status=200")
        return response
    except Exception:
        INFERENCE_ERRORS_TOTAL.labels(reason="inference_exception").inc()
        logger.exception("chat response status=500")
        raise


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
