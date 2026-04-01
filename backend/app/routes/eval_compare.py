from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..eval.compare import compare_routed_models
from ..routing import SUPPORTED_MODELS

router = APIRouter()


class EvalCompareRequest(BaseModel):
    prompt: str
    models: List[str] = Field(default_factory=lambda: list(SUPPORTED_MODELS))


@router.post("/v1/eval/compare")
def eval_compare(req: EvalCompareRequest) -> Dict[str, Any]:
    return compare_routed_models(prompt=req.prompt, models=req.models)
