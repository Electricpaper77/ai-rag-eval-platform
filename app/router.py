from __future__ import annotations

import itertools
import time
from dataclasses import dataclass

from app.adapters.base import BaseAdapter, BackendConfig, InferenceResult
from app.benchmark import BenchmarkRecorder, RequestRecord
from app.models import ChatCompletionRequest, RoutingPolicy
from app.reliability import CircuitBreaker


@dataclass
class RuntimeBackend:
    config: BackendConfig
    adapter: BaseAdapter
    circuit_breaker: CircuitBreaker

    @property
    def available(self) -> bool:
        return self.config.enabled and not self.circuit_breaker.is_open


class InferenceRouter:
    def __init__(self, backends: list[RuntimeBackend], recorder: BenchmarkRecorder):
        self.backends = backends
        self.recorder = recorder
        weighted_names = [
            backend.config.name
            for backend in self.backends
            for _ in range(max(1, backend.config.weight))
            if backend.config.enabled
        ]
        self._weighted_cycle = itertools.cycle(weighted_names or [backend.config.name for backend in self.backends])

    def candidates(self, request: ChatCompletionRequest, attempted: set[str] | None = None) -> list[RuntimeBackend]:
        attempted = attempted or set()
        available = [
            backend
            for backend in self.backends
            if backend.available
            and backend.config.name not in attempted
            and (not backend.config.model_aliases or request.model in backend.config.model_aliases)
        ]
        if not available:
            return []
        selected = self.select(request.routing_policy, available)
        rest = [backend for backend in available if backend.config.name != selected.config.name]
        return [selected, *self._fallback_order(rest)]

    def select(self, policy: RoutingPolicy, candidates: list[RuntimeBackend]) -> RuntimeBackend:
        if policy == "lowest_cost":
            return min(candidates, key=lambda backend: backend.config.cost_per_1k_tokens)
        if policy == "highest_quality":
            return max(candidates, key=lambda backend: backend.config.quality_score)
        if policy == "weighted_round_robin":
            for _ in range(len(candidates) * 8):
                name = next(self._weighted_cycle)
                for backend in candidates:
                    if backend.config.name == name:
                        return backend
            return candidates[0]
        if policy in {"lowest_latency", "fallback_on_error"}:
            return min(
                candidates,
                key=lambda backend: self.recorder.backend_latency(
                    backend.config.name,
                    backend.config.expected_latency_ms,
                ),
            )
        return candidates[0]

    def record_result(self, result: InferenceResult, policy: str, success: bool = True) -> None:
        self.recorder.record(
            RequestRecord(
                backend=result.backend,
                policy=policy,
                latency_seconds=result.latency_seconds,
                time_to_first_token_seconds=result.time_to_first_token_seconds,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                cost_usd=result.cost_usd,
                success=success,
                created_at=time.time(),
            )
        )

    def _fallback_order(self, backends: list[RuntimeBackend]) -> list[RuntimeBackend]:
        return sorted(backends, key=lambda backend: (backend.config.cost_per_1k_tokens, -backend.config.quality_score))

