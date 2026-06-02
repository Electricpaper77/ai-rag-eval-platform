from __future__ import annotations

import json


GPU_FIELDS = {
    "gpu_utilization_percent",
    "gpu_memory_used_mb",
    "gpu_memory_total_mb",
    "tokens_per_second",
    "inference_latency_p50_ms",
    "inference_latency_p95_ms",
    "queue_depth",
    "cold_start_count",
    "cost_per_1k_tokens",
    "requests_per_gpu_hour",
}


def test_gpu_status_returns_simulated_nvidia_observability_payload(client, tmp_path):
    response = client.get("/gpu/status")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "simulated"
    assert body["gpu_model"].startswith("NVIDIA")
    assert GPU_FIELDS.issubset(body)
    assert 0 <= body["gpu_utilization_percent"] <= 100
    assert body["gpu_memory_used_mb"] <= body["gpu_memory_total_mb"]
    assert body["tokens_per_second"] > 0
    assert body["inference_latency_p95_ms"] >= body["inference_latency_p50_ms"]

    log_path = tmp_path / "gpu_observability_runs.jsonl"
    assert log_path.exists()
    logged = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert GPU_FIELDS.issubset(logged)
    assert logged["gpu_id"] == body["gpu_id"]


def test_gpu_status_exports_prometheus_metrics(client):
    client.get("/gpu/status")
    text = client.get("/metrics").text

    for metric in GPU_FIELDS:
        assert metric in text
    assert 'gpu_id="gpu-0"' in text
    assert 'node="mock-a10g-node-1"' in text
