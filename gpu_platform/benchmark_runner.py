from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LATEST_BENCHMARK_PATH = Path("artifacts/benchmarks/gpu_real_run.json")


def load_latest_benchmark(path: Path | None = None) -> dict[str, Any]:
    benchmark_path = path or LATEST_BENCHMARK_PATH
    if not benchmark_path.exists():
        return {
            "runtime": "vllm",
            "model": "mistral-7b",
            "requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_time_sec": 0.0,
            "requests_per_sec": 0.0,
            "avg_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "tokens_per_second": 0.0,
            "artifact_path": str(benchmark_path),
        }

    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    payload.setdefault("artifact_path", str(benchmark_path))
    return payload
