from __future__ import annotations

import threading
import time
from typing import Any


class VLLMRuntimeAdapter:
    def __init__(self, model_name: str = "vllm-balanced", cost_per_1k_tokens: float = 0.14) -> None:
        self.model_name = model_name
        self.cost_per_1k_tokens = cost_per_1k_tokens
        self._tokens_per_second = 135.0
        self._p50_latency_ms = 620.0
        self._p95_latency_ms = 1120.0
        self._queue_depth = 0
        self._lock = threading.Lock()

    @property
    def tokens_per_second(self) -> float:
        return self._tokens_per_second

    @property
    def p50_latency_ms(self) -> float:
        return self._p50_latency_ms

    @property
    def p95_latency_ms(self) -> float:
        return self._p95_latency_ms

    @property
    def queue_depth(self) -> int:
        return self._queue_depth

    def generate(self, messages: list[dict[str, str]], max_tokens: int = 128, **_: Any) -> dict[str, Any]:
        prompt = " ".join(str(m.get("content", "")) for m in messages if isinstance(m, dict)).strip()
        prompt_tokens = max(1, len(prompt.split()))
        completion_tokens = max(8, min(max_tokens, int(prompt_tokens * 1.5) + 12))
        latency_ms = max(10.0, self.p50_latency_ms * (1 + (self.queue_depth * 0.08)))
        with self._lock:
            self._queue_depth += 1
        try:
            time.sleep(latency_ms / 1000.0)
            return {
                "model": self.model_name,
                "content": f"[vllm] {prompt or 'ping'}",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "latency_ms": latency_ms,
            }
        finally:
            with self._lock:
                self._queue_depth = max(0, self._queue_depth - 1)
