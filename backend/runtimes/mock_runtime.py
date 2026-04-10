from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from typing import Any, Dict, List

from .base import BaseRuntime


class MockRuntime(BaseRuntime):
    """Deterministic local runtime for infra validation and benchmarking."""

    backend_name = "mock"

    async def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        model: str,
    ) -> Dict[str, Any]:
        canonical_prompt = "\n".join(
            f"{m.get('role', 'user')}:{m.get('content', '')}" for m in messages
        )
        digest = hashlib.sha256(canonical_prompt.encode("utf-8")).hexdigest()

        prompt_tokens = max(1, len(canonical_prompt.split()))
        completion_tokens = min(max_tokens, 12 + (int(digest[0:2], 16) % 60))
        total_tokens = prompt_tokens + completion_tokens

        simulated_latency_ms = 100 + (int(digest[2:4], 16) % 301)
        await asyncio.sleep(simulated_latency_ms / 1000.0)

        user_message = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        assistant_text = (
            f"[mock-runtime] Deterministic response to: {user_message.strip() or 'empty prompt'} "
            f"| sig={digest[:10]} | temp={temperature:.2f}"
        )

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": assistant_text,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "backend": self.backend_name,
            "latency_ms": simulated_latency_ms,
        }
