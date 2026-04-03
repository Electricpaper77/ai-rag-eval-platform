from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from urllib import error, request

from backend.app.runtimes.mock_runtime import MockRuntime

logger = logging.getLogger("uvicorn.access")


class VLLMProvider:
    """OpenAI-compatible provider adapter for vLLM chat completions."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        upstream_model: str | None = None,
        fallback_provider: MockRuntime | None = None,
    ) -> None:
        normalized_base_url = (base_url or os.getenv("VLLM_BASE_URL", "http://localhost:8000")).rstrip("/")
        self.endpoint = f"{normalized_base_url}/v1/chat/completions"
        self.timeout_seconds = float(timeout_seconds or os.getenv("VLLM_TIMEOUT_SECONDS", 30))
        self.upstream_model = upstream_model or os.getenv("VLLM_MODEL", "default")
        self.fallback_provider = fallback_provider or MockRuntime()

    def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        start = time.perf_counter()
        model_name = kwargs.get("upstream_model", self.upstream_model)

        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
        }

        try:
            response_payload = self._post(payload)
            output = response_payload.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = response_payload.get("usage", {})
            tokens_generated = usage.get("completion_tokens") or len(output.split())
            latency_ms = (time.perf_counter() - start) * 1000

            self._log_event(
                model_name=model_name,
                latency_ms=latency_ms,
                tokens_generated=tokens_generated,
                fallback=False,
            )

            return {
                "output": output,
                "tokens_out": int(tokens_generated),
                "latency_ms": float(latency_ms),
            }
        except (error.URLError, error.HTTPError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
            fallback_result = self.fallback_provider.generate(prompt, **kwargs)
            self._log_event(
                model_name=model_name,
                latency_ms=fallback_result.get("latency_ms", 0.0),
                tokens_generated=fallback_result.get("tokens_out", 0),
                fallback=True,
                error_message=str(exc),
            )
            return fallback_result

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with request.urlopen(req, timeout=self.timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _log_event(
        self,
        *,
        model_name: str,
        latency_ms: float,
        tokens_generated: int,
        fallback: bool,
        error_message: str | None = None,
    ) -> None:
        event = {
            "event": "provider_inference",
            "provider": "vllm",
            "model_name": model_name,
            "latency_ms": round(float(latency_ms or 0.0), 3),
            "tokens_generated": int(tokens_generated or 0),
            "fallback_to_mock": fallback,
        }
        if error_message:
            event["error"] = error_message

        logger.info(json.dumps(event))
