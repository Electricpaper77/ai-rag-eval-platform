"""Thin GPU Lab adapter over the canonical NVIDIA evaluator request path."""
from __future__ import annotations
from nvidia_eval.runner import request_nim

class NvidiaNimProvider:
    mode = "authenticated"
    endpoint_host = "integrate.api.nvidia.com"
    def complete(self, prompt: str, model: str) -> dict:
        text, latency_ms = request_nim(model, prompt, {"temperature": 0})
        return {"text": text, "input_tokens": None, "output_tokens": None, "provider_latency_seconds": latency_ms / 1000}
