from __future__ import annotations

from typing import Literal

RuntimeType = Literal["vllm", "mock", "triton"]
SUPPORTED_RUNTIMES: tuple[RuntimeType, ...] = ("vllm", "mock", "triton")


def normalize_runtime_type(runtime_name: str | None) -> RuntimeType:
    normalized = (runtime_name or "mock").strip().lower()
    if normalized in SUPPORTED_RUNTIMES:
        return normalized  # type: ignore[return-value]
    raise ValueError(f"Unsupported runtime type: {runtime_name}")
