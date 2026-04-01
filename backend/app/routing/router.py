from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, Mapping, Protocol

logger = logging.getLogger("uvicorn.access")

SUPPORTED_MODELS = ("baseline", "fast", "eval")
DEFAULT_MODEL = "baseline"


@dataclass(frozen=True)
class BackendResult:
    response: str
    tokens_generated: int
    latency_ms: float


class ModelBackend(Protocol):
    """Typed contract for model-specific inference backends."""

    def generate(self, prompt: str) -> BackendResult:
        ...


class MockBackend:
    """Minimal backend implementation for local/mock routing behavior."""

    def __init__(self, *, label: str, response_text: str, delay_ms: float = 0.0) -> None:
        self.label = label
        self.response_text = response_text
        self.delay_ms = delay_ms

    def generate(self, prompt: str) -> BackendResult:
        start = time.perf_counter()
        if self.delay_ms > 0:
            time.sleep(self.delay_ms / 1000.0)

        # Include a short prompt echo for easier debugging while remaining deterministic.
        suffix = f" | prompt={prompt[:32]}" if prompt else ""
        response = f"{self.response_text}{suffix}"
        latency_ms = (time.perf_counter() - start) * 1000

        return BackendResult(
            response=response,
            tokens_generated=len(response.split()),
            latency_ms=latency_ms,
        )


class MultiModelRouter:
    """Route incoming inference requests to model-specific backends."""

    def __init__(self, backends: Mapping[str, ModelBackend], default_model: str = DEFAULT_MODEL) -> None:
        if default_model not in backends:
            raise ValueError(f"default_model '{default_model}' missing from backend registry")

        self._backends: Dict[str, ModelBackend] = {
            name.strip().lower(): backend for name, backend in backends.items()
        }
        self.default_model = default_model

    def resolve_backend(self, requested_model: str | None) -> tuple[str, ModelBackend]:
        normalized = (requested_model or "").strip().lower()
        selected_model = normalized if normalized in self._backends else self.default_model

        if normalized and normalized not in self._backends:
            logger.warning(
                "Unknown model '%s'; defaulting to '%s'",
                requested_model,
                self.default_model,
            )

        return selected_model, self._backends[selected_model]

    def generate(self, requested_model: str | None, prompt: str) -> tuple[str, BackendResult]:
        model_name, backend = self.resolve_backend(requested_model)
        result = backend.generate(prompt)

        logger.info(
            "multi_model_route model=%s backend=%s latency_ms=%.3f",
            model_name,
            backend.__class__.__name__,
            result.latency_ms,
        )
        return model_name, result


DEFAULT_ROUTER = MultiModelRouter(
    backends={
        "baseline": MockBackend(label="baseline", response_text="baseline backend response"),
        "fast": MockBackend(label="fast", response_text="optimized backend response"),
        "eval": MockBackend(label="eval", response_text="evaluation backend response"),
    }
)
