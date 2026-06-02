from __future__ import annotations

import abc
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from app.models import ChatCompletionChoice, ChatCompletionRequest, ChatCompletionResponse, ChatCompletionUsage


@dataclass(frozen=True)
class BackendConfig:
    name: str
    adapter: str
    endpoint: str | None = None
    api_key_env: str | None = None
    model_aliases: list[str] = field(default_factory=list)
    weight: int = 1
    cost_per_1k_tokens: float = 0.0
    quality_score: float = 0.5
    expected_latency_ms: float = 250.0
    timeout_seconds: float = 10.0
    enabled: bool = True


@dataclass
class InferenceResult:
    response: ChatCompletionResponse
    backend: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_seconds: float
    time_to_first_token_seconds: float
    cost_usd: float


class AdapterError(RuntimeError):
    pass


class BaseAdapter(abc.ABC):
    def __init__(self, config: BackendConfig):
        self.config = config

    @abc.abstractmethod
    async def complete(self, request: ChatCompletionRequest) -> InferenceResult:
        raise NotImplementedError

    async def stream_tokens(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        result = await self.complete(request)
        content = result.response.choices[0].message.content
        for token in content.split():
            await asyncio.sleep(0)
            yield f"{token} "

    async def health(self) -> bool:
        return True

    def _cost(self, total_tokens: int) -> float:
        return (total_tokens / 1000.0) * self.config.cost_per_1k_tokens

    def _usage(self, request: ChatCompletionRequest, content: str) -> ChatCompletionUsage:
        prompt_tokens = sum(max(1, len(message.content.split())) for message in request.messages)
        completion_tokens = max(1, len(content.split()))
        return ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    def _response(self, request: ChatCompletionRequest, content: str) -> ChatCompletionResponse:
        usage = self._usage(request, content)
        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message={"role": "assistant", "content": content},
                    finish_reason="stop",
                )
            ],
            usage=usage,
            backend=self.config.name,
            routing_policy=request.routing_policy,
        )


class MockLocalAdapter(BaseAdapter):
    async def complete(self, request: ChatCompletionRequest) -> InferenceResult:
        started = time.perf_counter()
        await asyncio.sleep(min(self.config.expected_latency_ms / 1000.0, 0.05))
        content = f"Mock response from {self.config.name} for model {request.model}."
        response = self._response(request, content)
        latency = time.perf_counter() - started
        usage = response.usage
        return InferenceResult(
            response=response,
            backend=self.config.name,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            latency_seconds=latency,
            time_to_first_token_seconds=min(latency, 0.02),
            cost_usd=self._cost(usage.total_tokens),
        )

    async def stream_tokens(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        content = f"Mock response from {self.config.name} for model {request.model}."
        for token in content.split():
            await asyncio.sleep(0.01)
            yield f"{token} "


class OpenAIAdapter(BaseAdapter):
    async def complete(self, request: ChatCompletionRequest) -> InferenceResult:
        if not self.config.endpoint:
            raise AdapterError(f"{self.config.name} has no endpoint configured")
        started = time.perf_counter()
        payload = request.model_dump(exclude={"routing_policy"}, exclude_none=True)
        headers = {"Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(self.config.endpoint, json=payload, headers=headers)
        if response.status_code >= 400:
            raise AdapterError(f"{self.config.name} returned HTTP {response.status_code}: {response.text[:200]}")
        body = response.json()
        parsed = ChatCompletionResponse(
            id=body.get("id", f"chatcmpl-{uuid.uuid4().hex[:24]}"),
            created=body.get("created", int(time.time())),
            model=body.get("model", request.model),
            choices=body["choices"],
            usage=body.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
            backend=self.config.name,
            routing_policy=request.routing_policy,
        )
        latency = time.perf_counter() - started
        return InferenceResult(
            response=parsed,
            backend=self.config.name,
            prompt_tokens=parsed.usage.prompt_tokens,
            completion_tokens=parsed.usage.completion_tokens,
            total_tokens=parsed.usage.total_tokens,
            latency_seconds=latency,
            time_to_first_token_seconds=latency,
            cost_usd=self._cost(parsed.usage.total_tokens),
        )


class VLLMAdapter(OpenAIAdapter):
    """vLLM exposes an OpenAI-compatible chat completions endpoint."""


class TritonAdapter(BaseAdapter):
    async def complete(self, request: ChatCompletionRequest) -> InferenceResult:
        if not self.config.endpoint:
            raise AdapterError(f"{self.config.name} has no Triton endpoint configured")
        started = time.perf_counter()
        prompt = "\n".join(f"{message.role}: {message.content}" for message in request.messages)
        payload: dict[str, Any] = {
            "inputs": [
                {
                    "name": "PROMPT",
                    "shape": [1, 1],
                    "datatype": "BYTES",
                    "data": [prompt],
                }
            ],
            "parameters": {"max_tokens": request.max_tokens or 256},
        }
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(self.config.endpoint, json=payload)
        if response.status_code >= 400:
            raise AdapterError(f"{self.config.name} returned HTTP {response.status_code}: {response.text[:200]}")
        body = response.json()
        content = self._extract_text(body)
        parsed = self._response(request, content)
        latency = time.perf_counter() - started
        return InferenceResult(
            response=parsed,
            backend=self.config.name,
            prompt_tokens=parsed.usage.prompt_tokens,
            completion_tokens=parsed.usage.completion_tokens,
            total_tokens=parsed.usage.total_tokens,
            latency_seconds=latency,
            time_to_first_token_seconds=latency,
            cost_usd=self._cost(parsed.usage.total_tokens),
        )

    def _extract_text(self, body: dict[str, Any]) -> str:
        outputs = body.get("outputs", [])
        if outputs and outputs[0].get("data"):
            return str(outputs[0]["data"][0])
        raise AdapterError(f"{self.config.name} returned no text output")


def build_adapter(config: BackendConfig) -> BaseAdapter:
    adapters = {
        "mock": MockLocalAdapter,
        "openai": OpenAIAdapter,
        "vllm": VLLMAdapter,
        "triton": TritonAdapter,
    }
    try:
        return adapters[config.adapter](config)
    except KeyError as exc:
        raise ValueError(f"Unsupported adapter type: {config.adapter}") from exc
