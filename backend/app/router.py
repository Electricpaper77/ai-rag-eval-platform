from __future__ import annotations

import os

from .runtimes import MockRuntime, OpenAIRuntime
from providers.vllm_provider import VLLMProvider


def _build_router() -> dict[str, object]:
    provider = os.getenv("PROVIDER", "openai").strip().lower()

    openai_runtime: object = OpenAIRuntime()
    if provider == "vllm":
        openai_runtime = VLLMProvider()

    return {
        "openai": openai_runtime,
        "vllm": VLLMProvider(),
        "mock": MockRuntime(),
        # Backward-compat aliases used by the existing evaluation harness/tests.
        "baseline": MockRuntime(),
        "fast": MockRuntime(),
        "eval": MockRuntime(),
    }


ROUTER = _build_router()


def run_inference(model_key: str, prompt: str, **kwargs):
    runtime = ROUTER.get((model_key or "").strip().lower())
    if not runtime:
        raise ValueError(f"unknown runtime {model_key}")
    return runtime.generate(prompt, **kwargs)
