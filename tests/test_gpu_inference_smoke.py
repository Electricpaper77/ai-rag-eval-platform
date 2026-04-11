from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app.main import app


client = TestClient(app)


def test_gpu_aware_chat_completion_and_metrics() -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "ping"}],
            "latency_budget_ms": 1500,
            "quality_tier": "balanced",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["routing"]["selected_runtime"] in {"triton", "vllm", "mock"}
    assert "explanation" in payload["routing"]

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.text
    assert "inference_requests_total" in body
    assert "inference_latency_seconds" in body
    assert "tokens_generated_total" in body
    assert "router_decisions_total" in body
    assert "gpu_queue_depth" in body
