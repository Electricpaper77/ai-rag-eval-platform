from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend.runtimes import MockRuntime

from .metrics import record_llm_api_metrics


DEFAULT_MODEL = "mock-llm"
DEFAULT_BACKEND = "mock"
INFERENCE_LOG_PATH = Path("artifacts/inference_logs.jsonl")


def _select_runtime() -> MockRuntime:
    backend = os.getenv("INFERENCE_BACKEND", DEFAULT_BACKEND).strip().lower()
    if backend != "mock":
        raise ValueError(f"unsupported inference backend '{backend}'")
    return MockRuntime()


def _append_inference_log(
    request_id: str,
    latency_ms: float,
    tokens_generated: int,
    backend: str,
    status: str,
) -> None:
    INFERENCE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "latency_ms": round(latency_ms, 3),
        "tokens_generated": tokens_generated,
        "backend": backend,
        "status": status,
    }
    with INFERENCE_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


async def handle_chat_completions(request_body: Dict[str, Any]) -> Dict[str, Any]:
    """Handle an OpenAI-compatible /v1/chat/completions request."""

    model = request_body.get("model") or DEFAULT_MODEL
    messages: List[Dict[str, str]] = request_body.get("messages") or []
    max_tokens = int(request_body.get("max_tokens", 256))
    temperature = float(request_body.get("temperature", 0.7))

    if not messages:
        raise ValueError("messages field required")

    runtime = _select_runtime()
    backend = runtime.backend_name

    start = time.perf_counter()
    status = "success"

    try:
        response = await runtime.generate(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            model=model,
        )
    except Exception:
        status = "error"
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000

    response["id"] = response.get("id") or f"chatcmpl-{uuid.uuid4().hex[:12]}"
    response["object"] = "chat.completion"
    response["model"] = model
    response["created"] = int(time.time())

    total_tokens = int(response.get("usage", {}).get("total_tokens", 0) or 0)

    record_llm_api_metrics(
        backend=backend,
        status=status,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
    )
    _append_inference_log(
        request_id=response["id"],
        latency_ms=latency_ms,
        tokens_generated=total_tokens,
        backend=backend,
        status=status,
    )

    response.pop("backend", None)
    response.pop("latency_ms", None)
    return response
