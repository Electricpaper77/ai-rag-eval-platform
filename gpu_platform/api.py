from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .gpu_job import GPUJobSpec
from .job_manager import get_job_status, list_jobs, submit_job
from .model_selector import select_best_model


class GPUJobPayload(BaseModel):
    job_id: str
    model_name: str
    gpu_count: int = Field(gt=0)
    replicas: int = Field(gt=0)
    container_image: str
    env: dict[str, str] = Field(default_factory=dict)
    resources: dict = Field(default_factory=dict)


router = APIRouter(prefix="/platform", tags=["platform-jobs"])


@router.post("/jobs")
def create_job(payload: GPUJobPayload) -> dict:
    spec = GPUJobSpec(**payload.model_dump())
    result = submit_job(spec)

    if result.get("status") == "fail":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/jobs")
def get_jobs() -> list[dict]:
    return list_jobs()


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    result = get_job_status(job_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return result


@router.get("/best-model")
def get_best_model() -> dict:
    return select_best_model()


app = FastAPI(title="GPU Platform Orchestration API")
app.include_router(router)
