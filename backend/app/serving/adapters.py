from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class AdapterConfig:
    endpoint: str
    model: str = "mock-llm"
    timeout_seconds: float = 10.0


class ServingAdapter:
    runtime_type = "unknown"

    def __init__(self, config: AdapterConfig):
        self.config = config

    def validate(self) -> None:
        parsed = urlparse(self.config.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("serving endpoint must be an absolute HTTP(S) URL")
        if self.config.timeout_seconds <= 0:
            raise ValueError("serving timeout must be positive")

    def build_request(self, messages: list[dict[str, Any]], model: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return {"model": model or self.config.model, "messages": messages, **kwargs}

    def parse_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(payload.get("choices"), list):
            raise ValueError("serving response must contain choices")
        return payload

    def status(self) -> dict[str, Any]:
        return {"runtime": self.runtime_type, "endpoint": self.config.endpoint, "status": "CONFIG_VALIDATED"}


class MockAdapter(ServingAdapter):
    runtime_type = "mock"


class OpenAICompatibleAdapter(ServingAdapter):
    runtime_type = "openai-compatible"


class VLLMAdapter(OpenAICompatibleAdapter):
    runtime_type = "vllm"


class TGIAdapter(ServingAdapter):
    runtime_type = "tgi"

    def build_request(self, messages: list[dict[str, Any]], model: str | None = None, **kwargs: Any) -> dict[str, Any]:
        prompt = "\n".join(str(message.get("content", "")) for message in messages)
        return {"inputs": prompt, "parameters": kwargs}

    def parse_response(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return {"choices": [{"message": {"role": "assistant", "content": payload[0].get("generated_text", "")}}]}
        raise ValueError("TGI response must contain generated_text")


class TritonAdapter(ServingAdapter):
    runtime_type = "triton"

    def build_request(self, messages: list[dict[str, Any]], model: str | None = None, **kwargs: Any) -> dict[str, Any]:
        prompt = "\n".join(str(message.get("content", "")) for message in messages)
        return {"inputs": [{"name": "TEXT", "shape": [1], "datatype": "BYTES", "data": [prompt]}]}

    def parse_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        outputs = payload.get("outputs") if isinstance(payload, dict) else None
        if not outputs:
            raise ValueError("Triton response must contain outputs")
        return {"choices": [{"message": {"role": "assistant", "content": outputs[0].get("data", [""])[0]}}]}


_ADAPTERS = {
    "mock": MockAdapter,
    "openai-compatible": OpenAICompatibleAdapter,
    "vllm": VLLMAdapter,
    "tgi": TGIAdapter,
    "triton": TritonAdapter,
}


def adapter_for(runtime: str, config: AdapterConfig) -> ServingAdapter:
    key = runtime.strip().lower()
    try:
        adapter = _ADAPTERS[key](config)
    except KeyError as exc:
        raise ValueError(f"unsupported serving runtime: {runtime}") from exc
    adapter.validate()
    return adapter


def validate_runtime_configs() -> list[dict[str, Any]]:
    configs = [
        ("vllm", "http://vllm.example.invalid:8000/v1"),
        ("tgi", "http://tgi.example.invalid:8080"),
        ("triton", "http://triton.example.invalid:8000/v2/models/model"),
    ]
    return [adapter_for(runtime, AdapterConfig(endpoint=endpoint)).status() for runtime, endpoint in configs]
