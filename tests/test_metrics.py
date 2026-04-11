from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app.main import app


client = TestClient(app)


def test_metrics_endpoint_exposes_prometheus_text(monkeypatch):
    monkeypatch.setenv("INFERENCE_BACKEND", "mock")

    client.post(
        "/v1/chat/completions",
        json={
            "model": "mock-llm",
            "messages": [{"role": "user", "content": "metrics please"}],
        },
    )

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "llm_requests_total" in response.text
    assert "llm_tokens_total" in response.text
    assert "llm_request_latency_seconds" in response.text
    assert "benchmark_runs_total" in response.text
    assert "benchmark_latency_ms" in response.text
    assert "benchmark_tokens_per_second" in response.text
