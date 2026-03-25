from __future__ import annotations

import time
from typing import Dict


class InferenceRuntime:
    def generate(self, prompt: str) -> Dict[str, object]:
        raise NotImplementedError


class SimulatedRuntime(InferenceRuntime):
    def generate(self, prompt: str) -> Dict[str, object]:
        start = time.perf_counter()
        response = "simulated output"
        tokens_generated = len(response.split())
        latency_ms = (time.perf_counter() - start) * 1000

        return {
            "response": response,
            "tokens_generated": tokens_generated,
            "latency_ms": latency_ms,
        }
