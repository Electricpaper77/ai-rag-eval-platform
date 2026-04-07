from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from gpu_platform.dynamic_batch_scheduler import schedule_requests
from gpu_platform.kv_cache_policy import decide_kv_cache_runtime, estimate_kv_cache_memory
from gpu_platform.parallelism_config import ParallelismConfig, estimate_gpu_memory_usage
from scripts.run_dynamic_batch_benchmark import run_benchmark


def test_dynamic_batch_scheduler_groups_and_utilization() -> None:
    queue = [
        {"request_id": "r1", "token_length": 96, "arrival_ms": 0, "latency_budget_ms": 600},
        {"request_id": "r2", "token_length": 110, "arrival_ms": 2, "latency_budget_ms": 600},
        {"request_id": "r3", "token_length": 520, "arrival_ms": 3, "latency_budget_ms": 900},
        {"request_id": "r4", "token_length": 500, "arrival_ms": 4, "latency_budget_ms": 900},
    ]

    result = schedule_requests(queue, batch_window_ms=10, max_batch_size=2, latency_sla_ms=1200)

    assert result["batch_groups"]
    assert 0.0 <= result["gpu_utilization_estimate"] <= 1.0
    assert result["expected_latency"] > 0


def test_kv_cache_policy_tier_decision() -> None:
    assert estimate_kv_cache_memory(1000) == 500.0

    high = decide_kv_cache_runtime(tokens_in_context=4000, max_batch_tokens=4096)
    low = decide_kv_cache_runtime(tokens_in_context=512, max_batch_tokens=4096)

    assert high["recommended_runtime"] == "high-memory-gpu-tier"
    assert low["recommended_runtime"] == "standard-gpu-tier"


def test_parallelism_memory_estimate() -> None:
    config = ParallelismConfig(tensor_parallel_size=2, pipeline_parallel_size=1, max_batch_tokens=4096)
    summary = estimate_gpu_memory_usage("13b", config)

    assert summary["total_model_memory_gb"] > summary["per_gpu_memory_gb"]
    assert summary["activation_overhead_gb"] > 0


def test_dynamic_batch_benchmark_artifact(tmp_path: Path) -> None:
    output = tmp_path / "dynamic_batch_summary.json"
    payload = run_benchmark(summary_path=output)

    assert output.exists()
    on_disk = json.loads(output.read_text(encoding="utf-8"))
    assert on_disk["scenarios"]
    assert payload["summary_generated_by"].endswith("run_dynamic_batch_benchmark.py")
