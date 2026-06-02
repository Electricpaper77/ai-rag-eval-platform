from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Protocol


GPU_METRIC_FIELDS = (
    "gpu_utilization_percent",
    "gpu_memory_used_mb",
    "gpu_memory_total_mb",
    "tokens_per_second",
    "inference_latency_p50_ms",
    "inference_latency_p95_ms",
    "queue_depth",
    "cold_start_count",
    "cost_per_1k_tokens",
    "requests_per_gpu_hour",
)


class GPUObservabilityProvider(Protocol):
    def collect(self) -> dict:
        """Return GPU/Kubernetes inference telemetry in a stable API shape."""


@dataclass
class SimulatedGPUObservabilityProvider:
    """Mock provider with a DCGM/Kubernetes-friendly interface."""

    gpu_id: str = "gpu-0"
    node: str = "mock-a10g-node-1"
    namespace: str = "ai-inference"
    pod: str = "inference-gateway-0"
    gpu_model: str = "NVIDIA A10G"
    memory_total_mb: int = 24576
    cost_per_1k_tokens_value: float = 0.00025
    _samples: int = 0

    def collect(self) -> dict:
        self._samples += 1
        phase = self._samples / 3
        utilization = round(68 + 12 * math.sin(phase), 2)
        memory_used = int(14200 + 720 * math.cos(phase))
        tokens_per_second = round(365 + 28 * math.sin(phase / 2), 2)
        latency_p50 = round(82 + 5 * math.cos(phase), 2)
        latency_p95 = round(latency_p50 + 38 + 3 * math.sin(phase), 2)
        queue_depth = max(0, int(5 + 3 * math.sin(phase)))

        return {
            "source": "simulated",
            "gpu_id": self.gpu_id,
            "node": self.node,
            "namespace": self.namespace,
            "pod": self.pod,
            "gpu_model": self.gpu_model,
            "collected_at_unix": time.time(),
            "gpu_utilization_percent": utilization,
            "gpu_memory_used_mb": memory_used,
            "gpu_memory_total_mb": self.memory_total_mb,
            "tokens_per_second": tokens_per_second,
            "inference_latency_p50_ms": latency_p50,
            "inference_latency_p95_ms": latency_p95,
            "queue_depth": queue_depth,
            "cold_start_count": 1 if self._samples == 1 else 0,
            "cost_per_1k_tokens": self.cost_per_1k_tokens_value,
            "requests_per_gpu_hour": round(tokens_per_second * 3600 / 512, 2),
        }
