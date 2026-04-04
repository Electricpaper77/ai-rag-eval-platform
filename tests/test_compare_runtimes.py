from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_compare_runtimes_writes_expected_artifacts() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/compare_runtimes.py"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    assert "| provider | p50 latency | tokens/sec | pass rate |" in result.stdout
    assert "| openai" in result.stdout
    assert "| vllm" in result.stdout
    assert "| mock" in result.stdout

    report_path = REPO_ROOT / "docs" / "benchmark_comparison.md"
    json_path = REPO_ROOT / "artifacts" / "proof" / "benchmark_comparison.json"

    assert report_path.exists()
    assert json_path.exists()

    report_text = report_path.read_text(encoding="utf-8")
    assert "| provider | pass_rate | p50_latency_ms | p95_latency_ms | tokens_per_sec |" in report_text

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["providers"] == ["openai", "vllm", "mock"]

    by_provider = {item["provider"]: item for item in payload["metrics"]}
    assert by_provider["openai"]["pass_rate"] == 0.89
    assert by_provider["openai"]["p50_latency"] == 850.0
    assert by_provider["openai"]["tokens_per_sec"] == 32.0

    assert by_provider["vllm"]["pass_rate"] == 0.87
    assert by_provider["vllm"]["p50_latency"] == 420.0
    assert by_provider["vllm"]["tokens_per_sec"] == 41.0
