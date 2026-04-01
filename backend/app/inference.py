from __future__ import annotations

import json
import logging
from typing import Any, Dict

from .metrics import record_inference_metrics
from .router import run_inference

logger = logging.getLogger("uvicorn.access")

DEFAULT_RUNTIME = "openai"


def handle_chat_completions(request_body: Dict[str, Any]) -> Dict[str, Any]:
    """Route chat inference through a runtime-agnostic layer for multi-backend evaluation."""
    messages = request_body.get("messages", [])
    if not messages:
        return {"error": "messages field required"}

    user_prompt = messages[-1]["content"]
    requested_runtime = request_body.get("model") or DEFAULT_RUNTIME

    try:
        result = run_inference(requested_runtime, user_prompt)
        resolved_runtime = (requested_runtime or "").strip().lower()
    except ValueError:
        # Backward compatibility: unknown runtimes fall back to mock baseline behavior.
        resolved_runtime = "mock"
        result = run_inference(resolved_runtime, user_prompt)

    tokens_out = int(result.get("tokens_out", 0) or 0)
    latency_ms = float(result.get("latency_ms", 0.0) or 0.0)

    record_inference_metrics(resolved_runtime, tokens_out, latency_ms, model_label=resolved_runtime)

    latency_seconds = max(latency_ms / 1000.0, 1e-9)
    tokens_per_second = tokens_out / latency_seconds
    logger.info(
        json.dumps(
            {
                "event": "inference_metrics",
                "runtime": resolved_runtime,
                "tokens_out": tokens_out,
                "latency_ms": round(latency_ms, 3),
                "tokens_per_second": round(tokens_per_second, 3),
            }
        )
    )

    return {
        "id": f"chatcmpl-{resolved_runtime}",
        "object": "chat.completion",
        "model_runtime": resolved_runtime,
        "latency_ms": latency_ms,
        "tokens_out": tokens_out,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.get("output", ""),
                },
            }
        ],
    }
