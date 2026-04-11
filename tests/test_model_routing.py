from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gpu_platform.model_registry as model_registry
import gpu_platform.request_router as request_router
from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_routing_fast_balanced_high_quality_with_registry(tmp_path: Path, monkeypatch) -> None:
    registry = tmp_path / "model_registry.yaml"
    registry.write_text(
        """
models:
  - id: fast_model
    provider: mock
    quality_score: 0.60
    avg_latency_ms: 200
    cost_per_1k_tokens: 0.09
  - id: balanced_model
    provider: mock
    quality_score: 0.92
    avg_latency_ms: 500
    cost_per_1k_tokens: 0.10
  - id: quality_model
    provider: mock
    quality_score: 0.95
    avg_latency_ms: 900
    cost_per_1k_tokens: 0.22
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(model_registry, "MODEL_REGISTRY_PATH", registry)

    payload = [{"role": "user", "content": "quick summary"}]

    fast = request_router.route_request(messages=payload, latency_budget_ms=1200, quality_tier="fast")
    balanced = request_router.route_request(messages=payload, latency_budget_ms=1200, quality_tier="balanced")
    hq = request_router.route_request(messages=payload, latency_budget_ms=1200, quality_tier="high_quality")

    assert fast["selected_backend"] == "fast_model"
    assert balanced["selected_backend"] == "balanced_model"
    assert hq["selected_backend"] == "quality_model"


def test_model_routing_metrics_are_exposed() -> None:
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "model_requests_total" in metrics.text
    assert "model_latency_seconds_bucket" in metrics.text
    assert "model_selection_count" in metrics.text
