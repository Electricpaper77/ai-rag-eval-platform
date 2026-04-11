from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class RuntimeInvocationResult:
    backend: str
    completion: str
    latency_ms: float
    tokens_generated: int
    tokens_per_second: float


class RuntimeBackend(Protocol):
    name: str

    def health_check(self) -> dict: ...

    def estimate_capacity(self) -> dict: ...

    def invoke_chat_completion(self, prompt: str, max_tokens: int = 256) -> RuntimeInvocationResult: ...

    def supported_hardware(self) -> list[str]: ...
