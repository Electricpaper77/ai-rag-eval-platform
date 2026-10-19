from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from .adapters import AdapterConfig, ServingAdapter, adapter_for


class ServingRuntime(ABC):
    """Stable interface shared by local and remote model-serving runtimes."""

    @abstractmethod
    async def health_check(self) -> bool: ...

    @abstractmethod
    async def readiness_check(self) -> bool: ...

    @abstractmethod
    async def generate(self, messages: list[dict[str, Any]], model: str, request_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def model_metadata(self) -> dict[str, Any]: ...

    @abstractmethod
    def metrics_metadata(self) -> dict[str, Any]: ...


class HttpServingRuntime(ServingRuntime):
    def __init__(self, runtime: str, config: AdapterConfig):
        self.adapter: ServingAdapter = adapter_for(runtime, config)

    async def _get(self, path: str) -> bool:
        async with httpx.AsyncClient(timeout=self.adapter.config.timeout_seconds) as client:
            response = await client.get(self.adapter.config.endpoint.rstrip("/") + path)
            return response.status_code == 200

    async def health_check(self) -> bool:
        return await self._get("/healthz")

    async def readiness_check(self) -> bool:
        return await self._get("/readyz")

    async def generate(self, messages: list[dict[str, Any]], model: str, request_id: str) -> dict[str, Any]:
        payload = self.adapter.build_request(messages, model=model, request_id=request_id)
        async with httpx.AsyncClient(timeout=self.adapter.config.timeout_seconds) as client:
            response = await client.post(self.adapter.config.endpoint.rstrip("/") + "/v1/chat/completions", json=payload, headers={"x-request-id": request_id})
            response.raise_for_status()
            return self.adapter.parse_response(response.json())

    def model_metadata(self) -> dict[str, Any]:
        return {"runtime": self.adapter.runtime_type, "model": self.adapter.config.model, "endpoint": self.adapter.config.endpoint}

    def metrics_metadata(self) -> dict[str, Any]:
        return {"runtime": self.adapter.runtime_type, "timeout_seconds": self.adapter.config.timeout_seconds}
