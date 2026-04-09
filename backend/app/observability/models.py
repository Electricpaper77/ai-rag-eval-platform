from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class InferenceRequestContext:
    request_id: str
    runtime: str
    model: str
    prompt_chars: int
    prompt_tokens_estimate: int


@dataclass(slots=True)
class InferencePerformanceMetrics:
    latency_ms: float
    queue_time_ms: float
    ttft_ms: float
    decode_time_ms: float
    tokens_out: int
    tokens_per_second: float


@dataclass(slots=True)
class InferenceEvent:
    event_time: str
    request: InferenceRequestContext
    performance: InferencePerformanceMetrics
    status: str
    error: str | None = None

    @classmethod
    def build(
        cls,
        request: InferenceRequestContext,
        performance: InferencePerformanceMetrics,
        status: str,
        error: str | None = None,
    ) -> "InferenceEvent":
        return cls(
            event_time=datetime.now(timezone.utc).isoformat(),
            request=request,
            performance=performance,
            status=status,
            error=error,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["runtime"] = self.request.runtime
        payload["model"] = self.request.model
        payload["request_id"] = self.request.request_id
        payload["latency_ms"] = self.performance.latency_ms
        payload["tokens_out"] = self.performance.tokens_out
        payload["tokens_per_second"] = self.performance.tokens_per_second
        return payload
