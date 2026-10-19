from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from .metrics import (
    DISTRIBUTED_REQUEST_LATENCY_SECONDS,
    DISTRIBUTED_REQUESTS_TOTAL,
    DISTRIBUTED_RETRIES_TOTAL,
    ROUTING_FAILURES_TOTAL,
    WORKER_REQUESTS_TOTAL,
)
from .models import RouteMetadata, utc_now
from .worker import WorkerRegistry, _WorkerRecord

router = APIRouter(prefix="/platform/distributed", tags=["distributed-inference"])
registry = WorkerRegistry.from_env()


async def _refresh() -> None:
    await registry.refresh()


def _routing_error(reason: str, detail: str) -> JSONResponse:
    ROUTING_FAILURES_TOTAL.labels(reason).inc()
    return JSONResponse(status_code=503, content={"error": {"reason_code": reason, "message": detail}})


def _route_metadata(record: _WorkerRecord, *, request_id: str, retry_count: int, policy: str | None = None) -> dict[str, Any]:
    return RouteMetadata(
        selected_worker_id=record.metadata.worker_id,
        policy=policy or registry.policy,
        worker_health=record.metadata.health,
        active_request_count=record.metadata.active_requests,
        route_timestamp=utc_now(),
        request_id=request_id,
        retry_count=retry_count,
    ).as_dict()


@router.get("/workers")
async def distributed_workers() -> dict[str, Any]:
    await _refresh()
    return {"workers": [worker.as_dict() for worker in registry.list_workers()]}


@router.get("/status")
async def distributed_status() -> dict[str, Any]:
    await _refresh()
    return registry.summary()


@router.post("/route")
async def distributed_route(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    await _refresh()
    request_id = str((payload or {}).get("request_id") or uuid.uuid4().hex)
    requested_policy = str((payload or {}).get("policy") or registry.policy)
    policy = requested_policy if requested_policy in {"round_robin", "least_requests"} else registry.policy
    record = registry.reserve(policy=policy)
    if record is None:
        reason = "all_workers_saturated" if registry.records and registry.healthy_workers() else "no_healthy_worker"
        return _routing_error(reason, "No schedulable worker is available")
    metadata = _route_metadata(record, request_id=request_id, retry_count=0, policy=policy)
    registry.release(record, success=True)
    return metadata


@router.post("/chat")
async def distributed_chat(payload: dict[str, Any], x_request_id: str | None = Header(default=None)) -> JSONResponse:
    started = time.perf_counter()
    request_id = x_request_id or str(payload.get("request_id") or f"gate7-{uuid.uuid4().hex[:12]}")
    await _refresh()
    attempted: set[str] = set()
    retry_count = 0
    last_error: Exception | None = None

    for attempt in range(2):
        record = registry.reserve(exclude=attempted)
        if record is None:
            reason = "all_workers_saturated" if registry.records and registry.healthy_workers() else "no_healthy_worker"
            DISTRIBUTED_REQUESTS_TOTAL.labels(registry.policy, "503").inc()
            DISTRIBUTED_REQUEST_LATENCY_SECONDS.labels(registry.policy, "503").observe(time.perf_counter() - started)
            return _routing_error(reason, "No schedulable worker is available")
        attempted.add(record.metadata.worker_id)
        metadata = _route_metadata(record, request_id=request_id, retry_count=retry_count)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{record.metadata.endpoint}/v1/chat/completions",
                    json=payload,
                    headers={"x-request-id": request_id},
                )
            if response.status_code >= 500:
                registry.release(record, success=False)
                WORKER_REQUESTS_TOTAL.labels(record.metadata.worker_id, "5xx").inc()
                DISTRIBUTED_REQUESTS_TOTAL.labels(registry.policy, str(response.status_code)).inc()
                DISTRIBUTED_REQUEST_LATENCY_SECONDS.labels(registry.policy, str(response.status_code)).observe(time.perf_counter() - started)
                try:
                    content = response.json()
                except ValueError:
                    content = {"error": response.text}
                return JSONResponse(status_code=response.status_code, content=content)
            response.raise_for_status()
            registry.release(record, success=True)
            WORKER_REQUESTS_TOTAL.labels(record.metadata.worker_id, "success").inc()
            body = response.json()
            body["distributed_routing"] = metadata
            body["distributed_routing"]["retry_count"] = retry_count
            DISTRIBUTED_REQUESTS_TOTAL.labels(registry.policy, "success").inc()
            DISTRIBUTED_REQUEST_LATENCY_SECONDS.labels(registry.policy, "success").observe(time.perf_counter() - started)
            return JSONResponse(status_code=response.status_code, content=body)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.NetworkError) as exc:
            last_error = exc
            registry.release(record, success=False)
            registry.mark_connection_failure(record, exc)
            WORKER_REQUESTS_TOTAL.labels(record.metadata.worker_id, "connection_error").inc()
            if attempt == 0:
                retry_count = 1
                DISTRIBUTED_RETRIES_TOTAL.labels(registry.policy).inc()
                await _refresh()
                continue
            break
        except Exception as exc:
            last_error = exc
            registry.release(record, success=False)
            break

    DISTRIBUTED_REQUESTS_TOTAL.labels(registry.policy, "503").inc()
    DISTRIBUTED_REQUEST_LATENCY_SECONDS.labels(registry.policy, "503").observe(time.perf_counter() - started)
    return _routing_error("worker_connection_failed", f"Worker forwarding failed: {type(last_error).__name__}")
