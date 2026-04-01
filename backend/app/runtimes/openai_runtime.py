from __future__ import annotations

import json
import os
import time
from urllib import request

from .base_runtime import BaseRuntime


class OpenAIRuntime(BaseRuntime):
    """Runtime wrapper for OpenAI-compatible chat completion endpoints."""

    def __init__(self, endpoint: str | None = None, upstream_model: str | None = None) -> None:
        self.endpoint = endpoint or os.getenv("OPENAI_COMPAT_ENDPOINT", "http://localhost:8000/v1/chat/completions")
        self.upstream_model = upstream_model or os.getenv("OPENAI_COMPAT_MODEL", "default")

    def generate(self, prompt: str, **kwargs) -> dict:
        start = time.perf_counter()
        payload = {
            "model": kwargs.get("upstream_model", self.upstream_model),
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

        output = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = result.get("usage", {})
        tokens_out = usage.get("completion_tokens") or len(output.split())
        latency_ms = (time.perf_counter() - start) * 1000

        return {
            "output": output,
            "tokens_out": int(tokens_out),
            "latency_ms": float(latency_ms),
        }
