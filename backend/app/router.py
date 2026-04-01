from __future__ import annotations

from .runtimes import MockRuntime, OpenAIRuntime

ROUTER = {
    "openai": OpenAIRuntime(),
    "mock": MockRuntime(),
    # Backward-compat aliases used by the existing evaluation harness/tests.
    "baseline": MockRuntime(),
    "fast": MockRuntime(),
    "eval": MockRuntime(),
}


def run_inference(model_key: str, prompt: str, **kwargs):
    runtime = ROUTER.get((model_key or "").strip().lower())
    if not runtime:
        raise ValueError(f"unknown runtime {model_key}")
    return runtime.generate(prompt, **kwargs)
