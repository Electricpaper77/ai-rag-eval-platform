from __future__ import annotations

import uuid

from .artifact_store import InferenceArtifactStore
from .models import InferenceEvent, InferenceRequestContext
from .performance import compute_performance_metrics, estimate_prompt_tokens
from ..metrics import record_inference_observability_metrics


class InferenceObservabilityService:
    def __init__(self, artifact_store: InferenceArtifactStore | None = None):
        self._artifact_store = artifact_store or InferenceArtifactStore()

    @property
    def artifact_store(self) -> InferenceArtifactStore:
        return self._artifact_store

    def build_request_context(self, runtime: str, model: str, prompt: str) -> InferenceRequestContext:
        return InferenceRequestContext(
            request_id=str(uuid.uuid4()),
            runtime=runtime,
            model=model,
            prompt_chars=len(prompt or ""),
            prompt_tokens_estimate=estimate_prompt_tokens(prompt),
        )

    def record_event(
        self,
        request_context: InferenceRequestContext,
        latency_ms: float,
        tokens_out: int,
        status: str = "ok",
        error: str | None = None,
    ) -> InferenceEvent:
        performance = compute_performance_metrics(latency_ms=latency_ms, tokens_out=tokens_out)
        event = InferenceEvent.build(
            request=request_context,
            performance=performance,
            status=status,
            error=error,
        )
        self._artifact_store.persist_event(event)

        record_inference_observability_metrics(
            runtime=request_context.runtime,
            model=request_context.model,
            status=status,
            queue_time_ms=performance.queue_time_ms,
            ttft_ms=performance.ttft_ms,
            decode_time_ms=performance.decode_time_ms,
            tokens_per_second=performance.tokens_per_second,
        )
        return event


INFERENCE_OBSERVABILITY = InferenceObservabilityService()
