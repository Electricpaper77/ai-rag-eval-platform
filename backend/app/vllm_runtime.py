from __future__ import annotations

import json
import time
from typing import Dict
from urllib import request

from .inference_runtime import InferenceRuntime


class VLLMRuntime(InferenceRuntime):
    """Inference runtime backed by a local OpenAI-compatible vLLM endpoint."""

    def __init__(self, endpoint: str = "http://localhost:8000/v1/chat/completions") -> None:
        self.endpoint = endpoint

    def generate(self, prompt: str) -> Dict[str, object]:
        start = time.perf_counter()

        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": prompt}],
        }
        body = json.dumps(payload).encode("utf-8")

        req = request.Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        response = result["choices"][0]["message"]["content"]

        usage = result.get("usage", {})
        tokens_generated = usage.get("completion_tokens")
        if tokens_generated is None:
            tokens_generated = len(response.split())

        latency_ms = (time.perf_counter() - start) * 1000

        return {
            "response": response,
            "tokens_generated": tokens_generated,
            "latency_ms": latency_ms,
        }
