from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .autoscaling import AutoscalingPolicySimulator, AutoscalingSignal
from .metrics_gpu_platform import (
    RoutingMetricEvent,
    record_admission_denial,
    record_autoscale_recommendation,
    record_routing_metrics,
)
from .runtime_adapters.amd_vllm_rocm import AMDROCmVLLMBackend
from .runtime_adapters.nvidia_dynamo_triton import NVIDIADynamoTritonBackend

ARTIFACT_DIR = Path("artifacts/proof")
ROUTING_JSONL = ARTIFACT_DIR / "routing_decisions.jsonl"
AUTOSCALE_JSONL = ARTIFACT_DIR / "autoscaling_recommendations.jsonl"
ADMISSION_JSONL = ARTIFACT_DIR / "admission_failures.jsonl"


class PlatformRouteRequest(BaseModel):
    prompt: str
    quality_tier: str = Field(default="balanced")
    latency_budget_ms: int = Field(default=1500, gt=0)
    max_tokens: int = Field(default=256, gt=0)
    queue_if_busy: bool = Field(default=False)


class ValidateDeploymentRequest(BaseModel):
    runtime: str
    gpu_count: int = Field(default=1, ge=1)
    replicas: int = Field(default=1, ge=1)


router = APIRouter(prefix="/platform", tags=["gpu-control-plane"])

_BACKENDS = {
    "nvidia_dynamo_triton": NVIDIADynamoTritonBackend(),
    "amd_vllm_rocm": AMDROCmVLLMBackend(),
}

_AUTOSCALER = AutoscalingPolicySimulator()
_REPLICAS = {key: 1 for key in _BACKENDS}


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def choose_backend(quality_tier: str, latency_budget_ms: int) -> str:
    nvidia = _BACKENDS["nvidia_dynamo_triton"].health_check()["status"] == "healthy"
    amd = _BACKENDS["amd_vllm_rocm"].health_check()["status"] == "healthy"

    if quality_tier in {"premium", "high"} and nvidia:
        return "nvidia_dynamo_triton"
    if quality_tier in {"cost", "economy"} and amd:
        return "amd_vllm_rocm"

    if latency_budget_ms <= 1000 and nvidia:
        return "nvidia_dynamo_triton"
    if amd:
        return "amd_vllm_rocm"
    return "nvidia_dynamo_triton"


def _handle_admission(runtime: str, queue_if_busy: bool) -> tuple[bool, str]:
    capacity = _BACKENDS[runtime].estimate_capacity()
    if capacity["available_slots"] > 0:
        return True, "accepted"

    reason = "queued" if queue_if_busy else "capacity_exceeded"
    if not queue_if_busy:
        record_admission_denial(runtime, reason)
        _append_jsonl(
            ADMISSION_JSONL,
            {
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "runtime": runtime,
                "reason": reason,
            },
        )
    return queue_if_busy, reason


@router.post("/route")
def route_request(payload: PlatformRouteRequest) -> dict:
    runtime = choose_backend(payload.quality_tier, payload.latency_budget_ms)
    admitted, admission_status = _handle_admission(runtime, payload.queue_if_busy)
    if not admitted:
        return {
            "status": "rejected",
            "runtime": runtime,
            "reason": admission_status,
        }

    completion = _BACKENDS[runtime].invoke_chat_completion(payload.prompt, max_tokens=payload.max_tokens)
    queue_depth = _BACKENDS[runtime].estimate_capacity()["queue_depth"]

    event = RoutingMetricEvent(
        backend=runtime,
        quality_tier=payload.quality_tier,
        decision="served",
        latency_ms=completion.latency_ms,
        tokens_per_second=completion.tokens_per_second,
        queue_depth=queue_depth,
    )
    record_routing_metrics(event)

    autoscale = _AUTOSCALER.recommend(
        AutoscalingSignal(
            backend=runtime,
            queue_depth=queue_depth,
            p95_latency_ms=completion.latency_ms,
            utilization=max(0.1, min(1.0, completion.tokens_generated / payload.max_tokens)),
        ),
        current_replicas=_REPLICAS[runtime],
    )
    _REPLICAS[runtime] = autoscale.target_replicas
    record_autoscale_recommendation(runtime, autoscale.action)

    routing_artifact = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "runtime": runtime,
        "latency_budget_ms": payload.latency_budget_ms,
        "quality_tier": payload.quality_tier,
        "latency_ms": completion.latency_ms,
        "tokens_per_sec": completion.tokens_per_second,
        "autoscale_action": autoscale.action,
        "admission_status": admission_status,
    }
    _append_jsonl(ROUTING_JSONL, routing_artifact)
    _append_jsonl(
        AUTOSCALE_JSONL,
        {
            "timestamp": routing_artifact["timestamp"],
            "runtime": runtime,
            "action": autoscale.action,
            "reason": autoscale.reason,
            "target_replicas": autoscale.target_replicas,
        },
    )

    return {
        "status": "ok",
        "runtime": runtime,
        "response": completion.completion,
        "latency_ms": completion.latency_ms,
        "tokens_generated": completion.tokens_generated,
        "tokens_per_sec": completion.tokens_per_second,
        "autoscaling": autoscale.__dict__,
    }


@router.post("/deployments/validate")
def validate_deployment(payload: ValidateDeploymentRequest) -> dict:
    runtime = payload.runtime
    if runtime not in _BACKENDS:
        return {"valid": False, "reason": "unsupported_runtime"}

    hardware = _BACKENDS[runtime].supported_hardware()
    valid = payload.gpu_count >= 1 and payload.replicas >= 1
    return {
        "valid": valid,
        "runtime": runtime,
        "supported_hardware": hardware,
        "requested": payload.model_dump(),
    }


@router.get("/status")
def platform_status() -> dict:
    return {
        "backends": {name: backend.health_check() for name, backend in _BACKENDS.items()},
        "replicas": _REPLICAS,
        "artifacts": {
            "routing": str(ROUTING_JSONL),
            "autoscaling": str(AUTOSCALE_JSONL),
            "admissions": str(ADMISSION_JSONL),
        },
    }
