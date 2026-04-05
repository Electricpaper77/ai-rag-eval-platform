from __future__ import annotations

from pydantic import BaseModel, Field


class CanaryPolicy(BaseModel):
    candidate_backend: str
    baseline_backend: str
    canary_percent: int = Field(ge=0, le=100)
    max_p95_latency_ms: float = Field(gt=0)
    min_pass_rate: float = Field(ge=0.0, le=1.0)
    max_hallucination_rate: float = Field(ge=0.0, le=1.0)
    rollback_enabled: bool = True
