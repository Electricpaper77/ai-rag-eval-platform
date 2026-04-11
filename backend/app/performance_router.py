from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .runtime_adapters.triton_runtime import TritonRuntimeAdapter
from .runtime_adapters.vllm_runtime import VLLMRuntimeAdapter

QualityTier = Literal["fast", "balanced", "high_quality"]


@dataclass
class RoutingDecision:
    selected_runtime: str
    selected_model: str
    quality_tier: QualityTier
    explanation: str
    model_cost_per_1k_tokens: float
    gpu_availability: bool

    def as_json(self) -> dict[str, object]:
        return {
            "selected_runtime": self.selected_runtime,
            "selected_model": self.selected_model,
            "quality_tier": self.quality_tier,
            "model_cost_per_1k_tokens": self.model_cost_per_1k_tokens,
            "gpu_availability": self.gpu_availability,
            "explanation": self.explanation,
        }


class PerformanceAwareRouter:
    def __init__(self) -> None:
        self._triton = TritonRuntimeAdapter()
        self._vllm = VLLMRuntimeAdapter()

    @property
    def runtimes(self) -> dict[str, object]:
        return {"triton": self._triton, "vllm": self._vllm}

    def route(self, latency_budget_ms: int, quality_tier: QualityTier, gpu_availability: bool = True) -> RoutingDecision:
        if not gpu_availability:
            return RoutingDecision(
                selected_runtime="mock",
                selected_model="mock-llm",
                quality_tier=quality_tier,
                model_cost_per_1k_tokens=0.0,
                gpu_availability=False,
                explanation="gpu_availability=false, routed to CPU-safe mock runtime",
            )

        if quality_tier == "fast" or latency_budget_ms <= self._triton.p95_latency_ms:
            return RoutingDecision(
                selected_runtime="triton",
                selected_model=self._triton.model_name,
                quality_tier=quality_tier,
                model_cost_per_1k_tokens=self._triton.cost_per_1k_tokens,
                gpu_availability=True,
                explanation="selected triton for strict latency budget / fast tier",
            )

        if quality_tier == "high_quality":
            return RoutingDecision(
                selected_runtime="vllm",
                selected_model=self._vllm.model_name,
                quality_tier=quality_tier,
                model_cost_per_1k_tokens=self._vllm.cost_per_1k_tokens,
                gpu_availability=True,
                explanation="selected vllm for high_quality tier with better output quality",
            )

        chosen = self._triton if self._triton.cost_per_1k_tokens <= self._vllm.cost_per_1k_tokens else self._vllm
        runtime_name = "triton" if chosen is self._triton else "vllm"
        return RoutingDecision(
            selected_runtime=runtime_name,
            selected_model=chosen.model_name,
            quality_tier=quality_tier,
            model_cost_per_1k_tokens=chosen.cost_per_1k_tokens,
            gpu_availability=True,
            explanation="selected lower-cost GPU runtime for balanced tier",
        )
