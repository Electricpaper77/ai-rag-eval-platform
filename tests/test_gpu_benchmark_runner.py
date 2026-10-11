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
    "requests_per_second",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "requests_attempted",
    "requests_succeeded",
    "failure_reason",
}

REQUIRED_PROOF_KEYS = {
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "tokens_per_sec",
    "runtime",
    "requests_per_sec",
}


def test_gpu_benchmark_runner_writes_valid_artifact(monkeypatch, tmp_path: Path) -> None:
    summary_path = tmp_path / "gpu_benchmark_summary.json"
    proof_dir = tmp_path / "proof"
    monkeypatch.setattr(run_gpu_benchmark, "SUMMARY_PATH", summary_path)
    monkeypatch.setattr(run_gpu_benchmark, "ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr(run_gpu_benchmark, "PROOF_DIR", proof_dir)
    monkeypatch.setattr(run_gpu_benchmark, "GPU_JSONL_PATH", proof_dir / "gpu_benchmark_run.jsonl")
    monkeypatch.setattr(run_gpu_benchmark, "GPU_SUMMARY_PATH", proof_dir / "gpu_summary.json")

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
    assert isinstance(payload["requests_per_second"], float)
    assert isinstance(payload["prompt_tokens"], int)
    assert isinstance(payload["completion_tokens"], int)
    assert isinstance(payload["total_tokens"], int)
    assert isinstance(payload["requests_attempted"], int)
    assert isinstance(payload["requests_succeeded"], int)
    assert isinstance(payload["failure_reason"], str)
    assert payload["prompt_tokens"] + payload["completion_tokens"] == payload["total_tokens"]
    assert payload["requests_succeeded"] == 10
    assert payload["total_tokens"] == 400
    assert payload["tokens_per_second"] > 0
    assert payload["requests_per_second"] > 0

    proof_rows = [
        json.loads(line)
        for line in run_gpu_benchmark.GPU_JSONL_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert proof_rows
    latest = proof_rows[-1]
    assert REQUIRED_PROOF_KEYS <= set(latest)
    assert latest["prompt_tokens"] == payload["prompt_tokens"]
    assert latest["completion_tokens"] == payload["completion_tokens"]
    assert latest["total_tokens"] == payload["total_tokens"]
    assert latest["tokens_per_sec"] == payload["tokens_per_second"]
    assert latest["requests_per_sec"] == payload["requests_per_second"]
    assert latest["prompt_tokens"] + latest["completion_tokens"] == latest["total_tokens"]
