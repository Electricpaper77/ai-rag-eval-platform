from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AutoscalingSignal:
    backend: str
    queue_depth: int
    p95_latency_ms: float
    utilization: float


@dataclass
class AutoscalingRecommendation:
    backend: str
    action: str
    reason: str
    target_replicas: int


class AutoscalingPolicySimulator:
    def __init__(
        self,
        min_replicas: int = 1,
        max_replicas: int = 20,
        queue_threshold: int = 25,
        p95_threshold_ms: float = 1500,
        low_utilization_threshold: float = 0.35,
    ) -> None:
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas
        self.queue_threshold = queue_threshold
        self.p95_threshold_ms = p95_threshold_ms
        self.low_utilization_threshold = low_utilization_threshold

    def recommend(self, signal: AutoscalingSignal, current_replicas: int) -> AutoscalingRecommendation:
        current_replicas = max(current_replicas, self.min_replicas)

        if signal.queue_depth > self.queue_threshold or signal.p95_latency_ms > self.p95_threshold_ms:
            target = min(current_replicas + 1, self.max_replicas)
            return AutoscalingRecommendation(
                backend=signal.backend,
                action="scale_up",
                reason="queue_or_latency_breach",
                target_replicas=target,
            )

        if signal.utilization < self.low_utilization_threshold and signal.queue_depth == 0:
            target = max(current_replicas - 1, self.min_replicas)
            return AutoscalingRecommendation(
                backend=signal.backend,
                action="scale_down",
                reason="sustained_low_utilization",
                target_replicas=target,
            )

        return AutoscalingRecommendation(
            backend=signal.backend,
            action="hold",
            reason="within_threshold",
            target_replicas=current_replicas,
        )
