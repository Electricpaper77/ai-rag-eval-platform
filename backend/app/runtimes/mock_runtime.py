from __future__ import annotations

from .base_runtime import BaseRuntime


class MockRuntime(BaseRuntime):
    """Deterministic runtime used by tests and local evaluation harnesses."""

    def generate(self, prompt: str, **kwargs) -> dict:
        return {
            "output": "mock response",
            "tokens_out": 20,
            "latency_ms": 50,
        }
