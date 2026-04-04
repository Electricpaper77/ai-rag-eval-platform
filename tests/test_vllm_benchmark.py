from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.vllm_benchmark_summary as vllm_benchmark_summary
import scripts.run_vllm_benchmark as run_vllm_benchmark


client = TestClient(app)


def test_vllm_benchmark_summary_contains_metrics_and_artifact(tmp_path: Path) -> None:
    config_path = tmp_path / "vllm_gpu_config.yaml"
    config_path.write_text(
        """
model: mistralai/Mistral-7B-Instruct-v0.2
max_model_len: 4096
tensor_parallel_size: 1
""".strip()
        + "\n",
        encoding="utf-8",
    )

    summary_path = tmp_path / "vllm_benchmark_summary.json"

    summary = run_vllm_benchmark.run_vllm_benchmark(config_path=config_path, summary_path=summary_path)

    assert summary_path.exists(), "benchmark json artifact not created"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))

    assert "avg_tokens_per_sec" in payload
    assert "avg_prefill_latency_ms" in payload
    assert "avg_decode_latency_ms" in payload
    assert "avg_request_latency_ms" in payload
    assert payload["num_requests"] > 0
    assert payload["requests"], "request-level metrics should be present"


def test_platform_vllm_benchmark_endpoint_returns_summary(tmp_path: Path, monkeypatch) -> None:
    summary_file = tmp_path / "vllm_benchmark_summary.json"
    expected = {
        "model": "mistralai/Mistral-7B-Instruct-v0.2",
        "avg_tokens_per_sec": 44.2,
        "p95_latency_ms": 1180,
        "avg_prefill_latency_ms": 320,
        "avg_decode_latency_ms": 860,
        "avg_request_latency_ms": 1180,
        "num_requests": 3,
        "requests": [],
    }
    summary_file.write_text(json.dumps(expected), encoding="utf-8")

    monkeypatch.setattr(vllm_benchmark_summary, "SUMMARY_PATH", summary_file)

    response = client.get("/platform/vllm-benchmark")
    assert response.status_code == 200
    assert response.json() == expected
