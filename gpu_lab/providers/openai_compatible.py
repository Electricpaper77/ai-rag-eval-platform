from __future__ import annotations
import os
from urllib.parse import urlparse
import httpx

class OpenAICompatibleProvider:
    mode = "authenticated"
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 60):
        self.base_url = (base_url or os.getenv("GPU_LAB_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.getenv("GPU_LAB_API_KEY") or ""
        self.timeout = timeout
    @property
    def endpoint_host(self): return urlparse(self.base_url).hostname
    def complete(self, prompt: str, model: str) -> dict:
        if not self.base_url or not self.api_key: raise ValueError("GPU_LAB_BASE_URL and GPU_LAB_API_KEY are required")
        response = httpx.post(self.base_url + "/chat/completions", headers={"Authorization": "Bearer " + self.api_key}, json={"model": model, "messages": [{"role":"user","content":prompt}], "temperature": 0}, timeout=self.timeout)
        response.raise_for_status(); data = response.json(); choice = data.get("choices", [{}])[0]
        return {"text": choice.get("message", {}).get("content"), "input_tokens": data.get("usage", {}).get("prompt_tokens"), "output_tokens": data.get("usage", {}).get("completion_tokens")}
