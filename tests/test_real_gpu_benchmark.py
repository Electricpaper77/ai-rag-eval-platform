from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.benchmark_runner as benchmark_runner


client = TestClient(app)


def test_load_latest_benchmark_defaults_when_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(benchmark_runner, "LATEST_BENCHMARK_PATH", missing)

    summary = benchmark_runner.load_latest_benchmark()

    assert summary["requests"] == 0
    assert summary["tokens_per_second"] == 0.0
    assert summary["artifact_path"].endswith("missing.json")


def test_latest_benchmark_endpoint_returns_artifact(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "gpu_real_run.json"
    expected = {
        "runtime": "vllm",
        "model": "mistral-7b",
        "requests": 50,
        "avg_latency_ms": 135,
        "p95_latency_ms": 260,
        "tokens_per_second": 58.4,
        "requests_per_sec": 18.2,
    }
    artifact.write_text(json.dumps(expected), encoding="utf-8")

    monkeypatch.setattr(benchmark_runner, "LATEST_BENCHMARK_PATH", artifact)

    response = client.get("/benchmark/latest")
    assert response.status_code == 200

    payload = response.json()
    assert payload["runtime"] == "vllm"
    assert payload["requests"] == 50
    assert payload["artifact_path"].endswith("gpu_real_run.json")
