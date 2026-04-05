from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib import request


class TritonRuntime:
    """HTTP adapter for Triton Inference Server using /v2/models/{model}/infer."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("TRITON_BASE_URL", "http://triton:8000")).rstrip("/")
        self.model_name = model_name or os.getenv("TRITON_MODEL", "llm")
        self.timeout_seconds = float(timeout_seconds or os.getenv("TRITON_TIMEOUT_SECONDS", 30))

    def endpoint(self, model_name: str | None = None) -> str:
        active_model = model_name or self.model_name
        return f"{self.base_url}/v2/models/{active_model}/infer"

    def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        chat_request = kwargs.get("chat_request")
        if not isinstance(chat_request, dict):
            chat_request = {
                "model": kwargs.get("model", self.model_name),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": kwargs.get("max_tokens", 256),
                "temperature": kwargs.get("temperature", 0.2),
            }

        return self.generate_chat(chat_request)

    def generate_chat(self, chat_request: dict[str, Any]) -> dict[str, Any]:
        start = time.perf_counter()
        model_name = str(chat_request.get("model") or self.model_name)
        payload = self._to_triton_payload(chat_request)
        response_payload = self._post(model_name=model_name, payload=payload)
        output_text = self._extract_text(response_payload)
        latency_ms = (time.perf_counter() - start) * 1000

        return {
            "runtime": "triton",
            "model": model_name,
            "output": output_text,
            "tokens_out": max(1, len(output_text.split())),
            "latency_ms": round(float(latency_ms), 3),
            "raw_response": response_payload,
        }

    def _to_triton_payload(self, chat_request: dict[str, Any]) -> dict[str, Any]:
        messages = chat_request.get("messages") or []
        prompt = "\n".join(
            f"{message.get('role', 'user')}: {message.get('content', '')}" for message in messages if isinstance(message, dict)
        ).strip()

        if not prompt:
            prompt = str(chat_request.get("prompt", ""))

        return {
            "inputs": [
                {
                    "name": "PROMPT",
                    "shape": [1, 1],
                    "datatype": "BYTES",
                    "data": [[prompt]],
                }
            ],
            "parameters": {
                "max_tokens": int(chat_request.get("max_tokens", 256)),
                "temperature": float(chat_request.get("temperature", 0.2)),
            },
        }

    def _post(self, model_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(
            self.endpoint(model_name),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _extract_text(self, response_payload: dict[str, Any]) -> str:
        outputs = response_payload.get("outputs") or []
        if not outputs:
            return ""

        first_output = outputs[0]
        data = first_output.get("data") or []
        if not data:
            return ""

        first_item = data[0]
        if isinstance(first_item, list) and first_item:
            return str(first_item[0])
        return str(first_item)
