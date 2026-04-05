from __future__ import annotations

import os

from .runtimes import MockRuntime, OpenAIRuntime
from runtimes.base import normalize_runtime_type
from runtimes.triton_runtime import TritonRuntime
from providers.vllm_provider import VLLMProvider


def _build_router() -> dict[str, object]:
    provider = os.getenv("PROVIDER", "openai").strip().lower()

    openai_runtime: object = OpenAIRuntime()
    if provider == "vllm":
        openai_runtime = VLLMProvider()

    triton_runtime: object = TritonRuntime()

    return {
        "openai": openai_runtime,
        "vllm": VLLMProvider(),
        "mock": MockRuntime(),
        "triton": triton_runtime,
        # Backward-compat aliases used by the existing evaluation harness/tests.
        "baseline": MockRuntime(),
        "fast": MockRuntime(),
        "eval": MockRuntime(),
    }


ROUTER = _build_router()


def run_inference(model_key: str, prompt: str, **kwargs):
    normalized_model_key = (model_key or "").strip().lower()
    if normalized_model_key in {"vllm", "mock", "triton"}:
        normalize_runtime_type(normalized_model_key)
    runtime = ROUTER.get(normalized_model_key)
    if not runtime:
        raise ValueError(f"unknown runtime {model_key}")
    return runtime.generate(prompt, **kwargs)
