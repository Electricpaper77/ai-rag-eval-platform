#!/usr/bin/env python3
"""Run dynamic batching simulation for low/medium/high load scenarios."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
import sys
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))

from gpu_platform.dynamic_batch_scheduler import schedule_requests

SUMMARY_PATH = Path("artifacts/gpu_optimization/dynamic_batch_summary.json")


SCENARIOS = {
    "low_load": {"num_requests": 12, "arrival_gap_ms": 18, "max_batch_size": 4},
    "medium_load": {"num_requests": 40, "arrival_gap_ms": 8, "max_batch_size": 8},
    "high_load": {"num_requests": 100, "arrival_gap_ms": 3, "max_batch_size": 12},
}


def _token_length(index: int) -> int:
    cycle = [96, 160, 256, 384, 640, 1024]
    return cycle[index % len(cycle)]


def _build_queue(num_requests: int, arrival_gap_ms: int) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for i in range(num_requests):
        queue.append(
            {
                "request_id": f"req-{i+1:03d}",
                "token_length": _token_length(i),
                "arrival_ms": i * arrival_gap_ms,
                "latency_budget_ms": 900 if i % 5 else 1200,
            }
        )
    return queue


def run_benchmark(summary_path: Path = SUMMARY_PATH) -> dict[str, Any]:
    scenario_rows: list[dict[str, Any]] = []

    for scenario_name, cfg in SCENARIOS.items():
        queue = _build_queue(cfg["num_requests"], cfg["arrival_gap_ms"])
        result = schedule_requests(
            queue,
            batch_window_ms=15,
            max_batch_size=cfg["max_batch_size"],
            latency_sla_ms=1200,
        )

        row = {
            "scenario": scenario_name,
            "batch_size": round(mean(group["batch_size"] for group in result["batch_groups"]), 2),
            "avg_latency": result["expected_latency"],
            "tokens_per_second": round(
                sum(item["token_length"] for item in queue)
                / max(0.001, (cfg["num_requests"] * cfg["arrival_gap_ms"]) / 1000),
                2,
            ),
            "gpu_utilization_estimate": result["gpu_utilization_estimate"],
        }
        scenario_rows.append(row)

    payload = {
        "summary_generated_by": "scripts/run_dynamic_batch_benchmark.py",
        "scenarios": scenario_rows,
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    summary = run_benchmark()
    print(json.dumps(summary, indent=2))
    print(f"Wrote dynamic batch summary to {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
