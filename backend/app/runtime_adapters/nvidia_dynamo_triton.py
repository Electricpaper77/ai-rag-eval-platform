from __future__ import annotations

import os
import time

from .base import RuntimeInvocationResult


class NVIDIADynamoTritonBackend:
    """Triton-compatible adapter for NVIDIA Dynamo style deployments."""

    def __init__(self, queue_depth: int = 0, healthy: bool = True) -> None:
        self.name = "nvidia_dynamo_triton"
        self.queue_depth = queue_depth
        self.healthy = healthy

    def health_check(self) -> dict:
        return {
            "backend": self.name,
            "status": "healthy" if self.healthy else "degraded",
            "queue_depth": self.queue_depth,
            "endpoint": os.getenv("NVIDIA_TRITON_URL", "http://triton.nvidia.svc.cluster.local:8000"),
        }

    def estimate_capacity(self) -> dict:
        max_inflight = int(os.getenv("NVIDIA_MAX_INFLIGHT", "128"))
        available = max(max_inflight - self.queue_depth, 0)
        return {
            "backend": self.name,
            "max_inflight": max_inflight,
            "queue_depth": self.queue_depth,
            "available_slots": available,
        }

    def invoke_chat_completion(self, prompt: str, max_tokens: int = 256) -> RuntimeInvocationResult:
        started = time.perf_counter()
        generated_tokens = min(max_tokens, max(8, len(prompt.split()) + 24))
        time.sleep(0.005)
        latency_ms = (time.perf_counter() - started) * 1000
        tps = generated_tokens / max(latency_ms / 1000.0, 1e-6)
        return RuntimeInvocationResult(
            backend=self.name,
            completion="NVIDIA Triton response",
            latency_ms=round(latency_ms, 2),
            tokens_generated=generated_tokens,
            tokens_per_second=round(tps, 2),
        )

    def supported_hardware(self) -> list[str]:
        return ["NVIDIA L4", "NVIDIA A100", "NVIDIA H100"]
