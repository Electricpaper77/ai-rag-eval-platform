from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend.runtimes import MockRuntime

from .metrics import (
    record_inference_metrics,
    record_llm_api_metrics,
    record_router_metrics,
)
from .performance_router import PerformanceAwareRouter

DEFAULT_MODEL = "mock-llm"
INFERENCE_LOG_PATH = Path("artifacts/inference_runs.jsonl")
_ROUTER = PerformanceAwareRouter()
_MOCK = MockRuntime()


def _append_inference_log(payload: dict[str, Any]) -> None:
    INFERENCE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INFERENCE_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def _cost_estimate(total_tokens: int, cost_per_1k_tokens: float) -> float:
    return round((max(total_tokens, 0) / 1000.0) * max(cost_per_1k_tokens, 0.0), 6)


async def handle_chat_completions(request_body: Dict[str, Any]) -> Dict[str, Any]:
    model = request_body.get("model") or DEFAULT_MODEL
    messages: List[Dict[str, str]] = request_body.get("messages") or []
    max_tokens = int(request_body.get("max_tokens", 128))
    temperature = float(request_body.get("temperature", 0.2))

    if not messages:
        raise ValueError("messages field required")

    latency_budget_ms = int(request_body.get("latency_budget_ms", 1500))
    quality_tier = str(request_body.get("quality_tier", "balanced")).strip().lower()
    if quality_tier not in {"fast", "balanced", "high_quality"}:
        quality_tier = "balanced"
    backend_override = os.getenv("INFERENCE_BACKEND", "").strip().lower()
    gpu_availability = bool(request_body.get("gpu_availability", backend_override != "mock"))

    decision = _ROUTER.route(
        latency_budget_ms=latency_budget_ms,
        quality_tier=quality_tier,
        gpu_availability=gpu_availability,
    )

    start = time.perf_counter()
    status = "success"
    backend = decision.selected_runtime

    try:
        if backend == "mock":
            response = await _MOCK.generate(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                model=model,
            )
            assistant_text = response["choices"][0]["message"]["content"]
            usage = response.get("usage", {})
            total_tokens = int(usage.get("total_tokens", 0))
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
            runtime_latency_ms = float(response.get("latency_ms", 0.0))
            tokens_per_second = round(total_tokens / max(runtime_latency_ms / 1000.0, 0.001), 3)
            queue_depth = 0
        else:
            runtime = _ROUTER.runtimes[backend]
            generated = runtime.generate(messages=messages, max_tokens=max_tokens)
            assistant_text = str(generated.get("content", ""))
            total_tokens = int(generated.get("total_tokens", 0))
            prompt_tokens = int(generated.get("prompt_tokens", 0))
            completion_tokens = int(generated.get("completion_tokens", 0))
            runtime_latency_ms = float(generated.get("latency_ms", 0.0))
            tokens_per_second = round(total_tokens / max(runtime_latency_ms / 1000.0, 0.001), 3)
            queue_depth = int(getattr(runtime, "queue_depth", 0))
    except Exception:
        status = "error"
        raise

    latency_ms = (time.perf_counter() - start) * 1000.0
    request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    cost_estimate = _cost_estimate(total_tokens=total_tokens, cost_per_1k_tokens=decision.model_cost_per_1k_tokens)

    record_llm_api_metrics(
        backend=backend,
        status=status,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
    )
    record_inference_metrics(
        runtime_label=backend,
        tokens_generated=total_tokens,
        latency_ms=latency_ms,
        model_label=decision.selected_model,
    )
    record_router_metrics(runtime=backend, quality_tier=quality_tier, queue_depth=queue_depth)

    _append_inference_log(
        {
            "request_id": request_id,
            "model": model,
            "latency_ms": round(latency_ms, 3),
            "tokens_per_second": tokens_per_second,
            "cost_estimate": cost_estimate,
            "success": status == "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": assistant_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
        "routing": decision.as_json(),
    }
