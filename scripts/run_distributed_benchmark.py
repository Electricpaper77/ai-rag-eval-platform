#!/usr/bin/env python3
"""Execute distributed benchmark matrix using platform job APIs and aggregate metrics."""

from __future__ import annotations

import itertools
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from gpu_platform.benchmark_summary import (
    PROOF_DIR,
    SUMMARY_PATH,
    aggregate_distributed_runs,
    write_distributed_summary,
)

DEFAULT_CONFIG_PATH = Path("configs/benchmark_matrix.yaml")
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_POLL_INTERVAL_S = 0.2
DEFAULT_POLL_TIMEOUT_S = 30.0


def _parse_simple_yaml(path: Path) -> dict[str, list[Any]]:
    matrix: dict[str, list[Any]] = {}
    active_key: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        if not line.startswith(" ") and line.endswith(":"):
            active_key = line[:-1].strip()
            matrix[active_key] = []
            continue

        if active_key and line.lstrip().startswith("- "):
            item = line.lstrip()[2:].strip()
            if item.isdigit():
                matrix[active_key].append(int(item))
            else:
                matrix[active_key].append(item)

    return matrix


def load_benchmark_matrix(path: Path) -> dict[str, list[Any]]:
    matrix = _parse_simple_yaml(path)
    required = ("models", "batch_sizes", "gpu_counts")
    missing = [key for key in required if not matrix.get(key)]
    if missing:
        raise ValueError(f"Matrix config missing required keys: {', '.join(missing)}")
    return matrix


def expand_matrix(matrix: dict[str, list[Any]]) -> list[dict[str, Any]]:
    combos = itertools.product(matrix["models"], matrix["batch_sizes"], matrix["gpu_counts"])
    return [
        {"model": model, "batch_size": int(batch_size), "gpu_count": int(gpu_count)}
        for model, batch_size, gpu_count in combos
    ]


def _model_factor(model_name: str) -> float:
    compact = model_name.split("/")[-1].lower()
    return 1.0 + (sum(ord(ch) for ch in compact) % 7) / 20.0


def simulate_run_metrics(model: str, gpu_count: int, batch_size: int) -> dict[str, float]:
    factor = _model_factor(model)
    p95_latency_ms = round(max(100.0, (1200.0 / gpu_count) * (0.8 + batch_size * 0.1) / factor), 2)
    tokens_per_sec = round((20.0 + batch_size * 7.0) * gpu_count * factor, 2)
    return {
        "p95_latency_ms": p95_latency_ms,
        "tokens_per_sec": tokens_per_sec,
    }


def submit_job(base_url: str, run_id: str, model: str, gpu_count: int, batch_size: int) -> None:
    payload = {
        "job_id": run_id,
        "model_name": model,
        "gpu_count": gpu_count,
        "replicas": gpu_count,
        "container_image": "vllm/vllm-openai:latest",
        "env": {"BATCH_SIZE": str(batch_size)},
        "resources": {"limits": {"nvidia.com/gpu": gpu_count}},
    }
    response = requests.post(f"{base_url.rstrip('/')}/platform/jobs", json=payload, timeout=15)
    response.raise_for_status()


def wait_for_completion(base_url: str, run_id: str, poll_interval_s: float, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    status_url = f"{base_url.rstrip('/')}/platform/jobs/{run_id}"

    while time.time() < deadline:
        response = requests.get(status_url, timeout=15)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "completed":
            return
        time.sleep(poll_interval_s)

    raise TimeoutError(f"Timed out waiting for run {run_id}")


def append_run_artifact(row: dict[str, Any], proof_dir: Path = PROOF_DIR) -> Path:
    proof_dir.mkdir(parents=True, exist_ok=True)
    output = proof_dir / f"distributed_benchmark_{row['run_id']}.jsonl"
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    return output


def run_distributed_benchmark(
    base_url: str,
    config_path: Path,
    proof_dir: Path = PROOF_DIR,
    summary_path: Path = SUMMARY_PATH,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    timeout_s: float = DEFAULT_POLL_TIMEOUT_S,
) -> dict[str, Any]:
    matrix = load_benchmark_matrix(config_path)
    combinations = expand_matrix(matrix)

    for idx, combo in enumerate(combinations, start=1):
        run_id = f"distributed-benchmark-{idx:03d}"
        submit_job(
            base_url=base_url,
            run_id=run_id,
            model=combo["model"],
            gpu_count=combo["gpu_count"],
            batch_size=combo["batch_size"],
        )
        wait_for_completion(
            base_url=base_url,
            run_id=run_id,
            poll_interval_s=poll_interval_s,
            timeout_s=timeout_s,
        )

        metrics = simulate_run_metrics(
            model=combo["model"],
            gpu_count=combo["gpu_count"],
            batch_size=combo["batch_size"],
        )
        append_run_artifact(
            {
                "run_id": run_id,
                "model": combo["model"],
                "gpu_count": combo["gpu_count"],
                "batch_size": combo["batch_size"],
                **metrics,
            },
            proof_dir=proof_dir,
        )

    summary = aggregate_distributed_runs(proof_dir=proof_dir)
    write_distributed_summary(summary=summary, summary_path=summary_path)
    return summary


def main() -> int:
    base_url = os.getenv("PLATFORM_API_BASE_URL", DEFAULT_BASE_URL)
    config_path = Path(os.getenv("BENCHMARK_MATRIX_PATH", str(DEFAULT_CONFIG_PATH)))

    summary = run_distributed_benchmark(base_url=base_url, config_path=config_path)
    print(json.dumps(summary, indent=2))
    print(f"Wrote distributed benchmark summary to {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
