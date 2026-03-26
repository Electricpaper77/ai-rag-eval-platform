from __future__ import annotations

from typing import Dict, Tuple

from .inference_runtime import InferenceRuntime, SimulatedRuntime
from .vllm_runtime import VLLMRuntime

BASELINE_MODEL = "baseline"

MODEL_REGISTRY: Dict[str, InferenceRuntime] = {
    BASELINE_MODEL: SimulatedRuntime(),
    "gpu": VLLMRuntime(),
}


def resolve_runtime(model_name: str | None) -> Tuple[str, InferenceRuntime]:
    normalized = (model_name or "").strip().lower()
    if normalized in MODEL_REGISTRY:
        return normalized, MODEL_REGISTRY[normalized]
    return BASELINE_MODEL, MODEL_REGISTRY[BASELINE_MODEL]
