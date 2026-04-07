from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class InferenceBackend(ABC):
    """Runtime abstraction for inference backends."""

    name: str

    @abstractmethod
    def infer(self, prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError


class MockInferenceBackend(InferenceBackend):
    name = "mock"

    def infer(self, prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "backend": self.name,
            "model": model,
            "output": f"mock-response:{prompt[:32]}",
            "tokens_generated": 16,
        }


class VLLMStyleBackend(InferenceBackend):
    name = "vllm-style"

    def infer(self, prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "backend": self.name,
            "model": model,
            "output": "placeholder-vllm-compatible-response",
            "tokens_generated": kwargs.get("max_tokens", 32),
            "note": "Interface placeholder for vLLM/Triton-compatible runtime adapters.",
        }
