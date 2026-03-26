from __future__ import annotations

import json
import logging
from typing import Any, Dict

from .metrics import record_inference_metrics
from .runtime_router import resolve_runtime

logger = logging.getLogger("uvicorn.access")


def handle_chat_completions(request_body: Dict[str, Any]) -> Dict[str, Any]:
    messages = request_body.get("messages", [])
    if not messages:
        return {"error": "messages field required"}

    user_prompt = messages[-1]["content"]
    model_name = request_body.get("model")
    runtime_label, runtime = resolve_runtime(model_name)
    result = runtime.generate(user_prompt)

    tokens_generated = int(result.get("tokens_generated") or 0)
    latency_ms = float(result.get("latency_ms") or 0.0)
    record_inference_metrics(runtime_label, tokens_generated, latency_ms)

    latency_seconds = max(latency_ms / 1000.0, 1e-9)
    tokens_per_second = tokens_generated / latency_seconds
    logger.info(
        json.dumps(
            {
                "event": "inference_metrics",
                "runtime": runtime_label,
                "tokens_generated": tokens_generated,
                "latency_ms": round(latency_ms, 3),
                "tokens_per_second": round(tokens_per_second, 3),
            }
        )
    )

    return {
        "id": f"chatcmpl-{runtime_label}",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result["response"],
                },
            }
        ],
    }
