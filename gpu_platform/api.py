from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .job_orchestrator import get_job, list_jobs, submit_job

from gpu_platform.canary_controller import CANARY_CONTROLLER
from gpu_platform.canary_policy import CanaryPolicy
from gpu_platform.request_router import route_request
from gpu_platform.shadow_eval import load_shadow_summary

from .benchmark_runner import load_latest_benchmark
from .benchmark_summary import load_distributed_summary
from .vllm_benchmark_summary import load_vllm_benchmark_summary
from .metrics import record_benchmark_summary
from .model_selector import select_best_model
from .job_status import platform_health_summary
from .dynamic_batch_scheduler import schedule_requests
from .kv_cache_policy import decide_kv_cache_runtime
from .parallelism_config import (
    EXAMPLE_PARALLELISM_CONFIG,
    ParallelismConfig,
    estimate_gpu_memory_usage,
)
from gpu_platform.placement_policy import (
    build_k8s_placement_spec,
    choose_gpu_tier,
    explain_placement_reason,
)


class PlatformJobPayload(BaseModel):
    workload_type: str
    image: str
    model: str
    gpu_count: int
    cpu: str
    memory: str
    pvc_size: str
    storage_class: str
    node_selector: dict[str, str] = Field(default_factory=dict)
    tolerations: list[dict] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    command: list[str] = Field(default_factory=list)
    retries: int = Field(default=0, ge=0)
    replicas: int = Field(default=1, ge=1)
    gpu_per_replica: int = Field(default=1, ge=1)
    tensor_parallel: int = Field(default=1, ge=1)
    pipeline_parallel: int = Field(default=1, ge=1)
    data_parallel: int = Field(default=1, ge=1)
    placement_group: str = Field(default="default")
    worker_group: str = Field(default="default")
    priority_class: str = Field(default="balanced")
    oversubscribed: bool = Field(default=False)
    oversubscription_reason_code: str | None = Field(default=None)



class PlatformChatRequest(BaseModel):
    messages: list[dict]
    latency_budget_ms: int = Field(default=1500, gt=0)
    quality_tier: str = Field(default="balanced")
    force_shadow: bool = Field(default=False)


class StartCanaryRequest(BaseModel):
    baseline_backend: str
    candidate_backend: str
    canary_percent: int = Field(ge=0, le=100)
    max_p95_latency_ms: float = Field(gt=0)
    min_pass_rate: float = Field(ge=0.0, le=1.0)
    max_hallucination_rate: float = Field(ge=0.0, le=1.0)


router = APIRouter(prefix="/platform", tags=["platform-jobs"])
summary_router = APIRouter(prefix="/eval", tags=["evaluation"])
benchmark_router = APIRouter(tags=["benchmark"])


@router.post("/jobs")
def create_job(payload: PlatformJobPayload) -> dict:
    job = submit_job(payload.model_dump())
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "preflight_status": "pass" if job["status"] == "succeeded" else "fail",
        "topology_summary": job.get("topology_summary"),
        "total_gpu_requested": job.get("total_gpu_requested"),
        "parallelism_config": job.get("parallelism_config"),
        "priority_class": job.get("priority_class"),
        "admission_decision": job.get("admission_decision"),
        "rejection_reason": job.get("rejection_reason"),
    }


@router.get("/jobs")
def get_jobs() -> list[dict]:
    return list_jobs()


@router.get("/jobs/{job_id}")
def get_job_by_id(job_id: str) -> dict:
    result = get_job(job_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return result


@router.get("/placement/example")
def get_placement_example() -> dict:
    decision = choose_gpu_tier(latency_budget_ms=900, quality_tier="balanced", runtime="vllm")
    placement = build_k8s_placement_spec(job_type="inference", gpu_tier=decision["gpu_tier"])
    explanation = explain_placement_reason(
        latency_budget_ms=900,
        quality_tier="balanced",
        runtime="vllm",
        job_type="inference",
        gpu_tier=decision["gpu_tier"],
    )
    return {
        "decision": decision,
        "placement": placement,
        "explanation": explanation,
    }


@router.get("/capacity")
def get_capacity_summary() -> dict:
    return {
        "available_placement_modes": [
            "nodeSelector+toleration",
            "nodeAffinity+toleration",
        ],
        "default_gpu_tier": "standard",
        "namespace_quota_summary": {
            "resource_quota": "gpu-capacity-quota",
            "max_gpu_requests": 8,
            "max_gpu_limits": 8,
            "cpu_request_budget": "24",
            "memory_request_budget": "96Gi",
        },
        "concurrency_assumptions": {
            "inference_replicas": 2,
            "batch_jobs_parallelism": 2,
            "max_concurrent_gpu_workloads": 8,
        },
    }


@router.get("/summary")
def get_platform_summary() -> dict:
    return platform_health_summary()


@router.get("/best-model")
def get_best_model() -> dict:
    return select_best_model()


@router.get("/benchmark-summary")
def get_benchmark_summary() -> dict:
    summary = load_distributed_summary()
    record_benchmark_summary(summary)
    return summary


@router.get("/vllm-benchmark")
def get_vllm_benchmark() -> dict:
    return load_vllm_benchmark_summary()


@router.get("/gpu/optimization_summary")
def get_gpu_optimization_summary() -> dict:
    sample_queue = [
        {"request_id": "req-a", "token_length": 128, "arrival_ms": 0, "latency_budget_ms": 900},
        {"request_id": "req-b", "token_length": 320, "arrival_ms": 5, "latency_budget_ms": 900},
        {"request_id": "req-c", "token_length": 960, "arrival_ms": 12, "latency_budget_ms": 1200},
        {"request_id": "req-d", "token_length": 256, "arrival_ms": 15, "latency_budget_ms": 900},
        {"request_id": "req-e", "token_length": 512, "arrival_ms": 19, "latency_budget_ms": 900},
    ]
    scheduler = schedule_requests(sample_queue, batch_window_ms=15, max_batch_size=4, latency_sla_ms=1200)
    avg_batch_size = (
        round(sum(group["batch_size"] for group in scheduler["batch_groups"]) / len(scheduler["batch_groups"]), 2)
        if scheduler["batch_groups"]
        else 0.0
    )
    parallelism = ParallelismConfig(**EXAMPLE_PARALLELISM_CONFIG)
    kv_summary = decide_kv_cache_runtime(tokens_in_context=3072, max_batch_tokens=parallelism.max_batch_tokens)
    memory_summary = estimate_gpu_memory_usage(model_size="13b", parallelism_config=parallelism)

    return {
        "recommended_batch_size": avg_batch_size,
        "kv_cache_estimate": kv_summary,
        "parallelism_config": parallelism.to_dict(),
        "parallelism_memory_estimate": memory_summary,
        "expected_tokens_per_second": round(1200.0 * max(0.5, scheduler["gpu_utilization_estimate"]), 2),
    }


@router.post("/canary/start")
def start_canary(payload: StartCanaryRequest) -> dict:
    policy = CanaryPolicy(
        candidate_backend=payload.candidate_backend,
        baseline_backend=payload.baseline_backend,
        canary_percent=payload.canary_percent,
        max_p95_latency_ms=payload.max_p95_latency_ms,
        min_pass_rate=payload.min_pass_rate,
        max_hallucination_rate=payload.max_hallucination_rate,
        rollback_enabled=True,
    )
    return CANARY_CONTROLLER.start(policy)


@router.get("/canary/status")
def canary_status() -> dict:
    return CANARY_CONTROLLER.status()


@router.post("/canary/stop")
def stop_canary() -> dict:
    return CANARY_CONTROLLER.stop()


@router.post("/chat")
def platform_chat(payload: PlatformChatRequest) -> dict:
    return route_request(
        messages=payload.messages,
        latency_budget_ms=payload.latency_budget_ms,
        quality_tier=payload.quality_tier,
        force_shadow=payload.force_shadow,
    )


@summary_router.get("/shadow-summary")
def shadow_summary() -> dict[str, float]:
    return load_shadow_summary()


@benchmark_router.get("/benchmark/latest")
def get_latest_benchmark() -> dict:
    return load_latest_benchmark()


app = FastAPI(title="GPU Platform Orchestration API")
app.include_router(router)
app.include_router(summary_router)
app.include_router(benchmark_router)
