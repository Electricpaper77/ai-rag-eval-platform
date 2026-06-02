from __future__ import annotations

import os
from pathlib import Path

from app.adapters.base import BackendConfig


ARTIFACT_DIR = Path(os.getenv("ARTIFACT_DIR", "docs/artifacts"))


def default_backends() -> list[BackendConfig]:
    """Local-first defaults; external backends activate by setting endpoints."""
    return [
        BackendConfig(
            name="mock-local",
            adapter="mock",
            model_aliases=["gpt-4o-mini", "llama-3.1-8b", "mixtral-8x7b"],
            weight=3,
            cost_per_1k_tokens=0.0001,
            quality_score=0.70,
            expected_latency_ms=45,
        ),
        BackendConfig(
            name="vllm-a10g",
            adapter="vllm" if os.getenv("VLLM_ENDPOINT") else "mock",
            endpoint=os.getenv("VLLM_ENDPOINT"),
            model_aliases=["llama-3.1-8b", "gpt-4o-mini"],
            weight=5,
            cost_per_1k_tokens=0.00025,
            quality_score=0.82,
            expected_latency_ms=85,
        ),
        BackendConfig(
            name="triton-h100",
            adapter="triton" if os.getenv("TRITON_ENDPOINT") else "mock",
            endpoint=os.getenv("TRITON_ENDPOINT"),
            model_aliases=["mixtral-8x7b", "gpt-4o-mini"],
            weight=2,
            cost_per_1k_tokens=0.0004,
            quality_score=0.88,
            expected_latency_ms=70,
        ),
        BackendConfig(
            name="openai",
            adapter="openai" if os.getenv("OPENAI_COMPAT_ENDPOINT") else "mock",
            endpoint=os.getenv("OPENAI_COMPAT_ENDPOINT"),
            api_key_env="OPENAI_API_KEY",
            model_aliases=["gpt-4o-mini"],
            weight=1,
            cost_per_1k_tokens=0.0006,
            quality_score=0.95,
            expected_latency_ms=180,
        ),
    ]

