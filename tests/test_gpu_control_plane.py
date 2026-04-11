from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.autoscaling import AutoscalingPolicySimulator, AutoscalingSignal
from backend.app.control_plane import _BACKENDS, choose_backend
from backend.app.main import app


client = TestClient(app)


def test_runtime_selection_prefers_nvidia_for_high_quality() -> None:
    selected = choose_backend(quality_tier="high", latency_budget_ms=2000)
    assert selected == "nvidia_dynamo_triton"


def test_runtime_selection_prefers_amd_for_cost_tier() -> None:
    selected = choose_backend(quality_tier="cost", latency_budget_ms=2000)
    assert selected == "amd_vllm_rocm"


def test_overload_handling_rejects_when_capacity_exceeded() -> None:
    backend = _BACKENDS["amd_vllm_rocm"]
    original_depth = backend.queue_depth
    backend.queue_depth = backend.estimate_capacity()["max_inflight"]
    try:
        response = client.post(
            "/platform/route",
            json={
                "prompt": "overload test",
                "quality_tier": "cost",
                "latency_budget_ms": 1700,
                "queue_if_busy": False,
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"
    finally:
        backend.queue_depth = original_depth


def test_autoscaling_decision_scale_up() -> None:
    simulator = AutoscalingPolicySimulator(queue_threshold=10, p95_threshold_ms=1200)
    rec = simulator.recommend(
        AutoscalingSignal(
            backend="nvidia_dynamo_triton",
            queue_depth=20,
            p95_latency_ms=1400,
            utilization=0.8,
        ),
        current_replicas=2,
    )
    assert rec.action == "scale_up"
    assert rec.target_replicas == 3


def test_metrics_emission_includes_gpu_platform_metrics() -> None:
    route = client.post(
        "/platform/route",
        json={
            "prompt": "metrics validation",
            "quality_tier": "balanced",
            "latency_budget_ms": 1200,
            "queue_if_busy": True,
        },
    )
    assert route.status_code == 200

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.text
    assert "gpu_platform_requests_total" in body
    assert "gpu_platform_latency_ms" in body
    assert "gpu_platform_tokens_per_second" in body
    assert "gpu_platform_admission_denials_total" in body
    assert "gpu_platform_autoscale_recommendations_total" in body
