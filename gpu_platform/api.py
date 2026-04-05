from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from gpu_platform.canary_controller import CANARY_CONTROLLER
from gpu_platform.canary_policy import CanaryPolicy
from gpu_platform.request_router import route_request
from gpu_platform.shadow_eval import load_shadow_summary

from .benchmark_runner import load_latest_benchmark
from .benchmark_summary import load_distributed_summary
from .vllm_benchmark_summary import load_vllm_benchmark_summary
from .gpu_job import GPUJobSpec
from .job_manager import get_job_status, list_jobs, submit_job
from .metrics import record_benchmark_summary, record_gpu_job_completion, record_gpu_job_submitted
from .model_selector import select_best_model
from .job_status import platform_health_summary


class GPUJobPayload(BaseModel):
    job_id: str
    model_name: str
    gpu_count: int = Field(gt=0)
    replicas: int = Field(gt=0)
    container_image: str
    env: dict[str, str] = Field(default_factory=dict)
    resources: dict = Field(default_factory=dict)


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
def create_job(payload: GPUJobPayload) -> dict:
    spec = GPUJobSpec(**payload.model_dump())
    result = submit_job(spec)

    if result.get("status") == "fail":
        raise HTTPException(status_code=400, detail=result)

    record_gpu_job_submitted()
    return result


@router.get("/jobs")
def get_jobs() -> list[dict]:
    jobs = list_jobs()
    for job in jobs:
        if job.get("status") == "completed":
            record_gpu_job_completion(job_id=job["job_id"], duration_seconds=float(job.get("duration_seconds", 0.0)))
    return jobs


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    result = get_job_status(job_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if result.get("status") == "completed":
        record_gpu_job_completion(job_id=result["job_id"], duration_seconds=float(result.get("duration_seconds", 0.0)))
    return result




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
