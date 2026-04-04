from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from gpu_platform.request_router import route_request

from .benchmark_summary import load_distributed_summary
from .vllm_benchmark_summary import load_vllm_benchmark_summary
from .gpu_job import GPUJobSpec
from .job_manager import get_job_status, list_jobs, submit_job
from .metrics import record_benchmark_summary, record_gpu_job_completion, record_gpu_job_submitted
from .model_selector import select_best_model


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


router = APIRouter(prefix="/platform", tags=["platform-jobs"])


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


@router.post("/chat")
def platform_chat(payload: PlatformChatRequest) -> dict:
    return route_request(
        messages=payload.messages,
        latency_budget_ms=payload.latency_budget_ms,
        quality_tier=payload.quality_tier,
    )


app = FastAPI(title="GPU Platform Orchestration API")
app.include_router(router)
