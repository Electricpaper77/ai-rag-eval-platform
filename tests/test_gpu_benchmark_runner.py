from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import scripts.run_gpu_benchmark as run_gpu_benchmark


REQUIRED_KEYS = {
    "success_rate",
    "avg_latency_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "tokens_per_second",
    "requests_attempted",
    "requests_succeeded",
    "failure_reason",
}


def test_gpu_benchmark_runner_writes_valid_artifact(monkeypatch, tmp_path: Path) -> None:
    summary_path = tmp_path / "gpu_benchmark_summary.json"
    monkeypatch.setattr(run_gpu_benchmark, "SUMMARY_PATH", summary_path)
    monkeypatch.setattr(run_gpu_benchmark, "ARTIFACT_DIR", tmp_path)

    summary = run_gpu_benchmark.run_benchmark(
        base_url="http://127.0.0.1:8000",
        requests_total=10,
        concurrency=5,
        quality_tier="fast",
        spawn_server=False,
        use_mock_runtime=True,
    )

    assert summary["success_rate"] > 0
    assert summary_path.exists()

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert set(payload.keys()) == REQUIRED_KEYS
    assert isinstance(payload["success_rate"], float)
    assert isinstance(payload["avg_latency_ms"], float)
    assert isinstance(payload["p50_latency_ms"], float)
    assert isinstance(payload["p95_latency_ms"], float)
    assert isinstance(payload["tokens_per_second"], float)
    assert isinstance(payload["requests_attempted"], int)
    assert isinstance(payload["requests_succeeded"], int)
    assert isinstance(payload["failure_reason"], str)
