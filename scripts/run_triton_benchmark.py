#!/usr/bin/env python3
"""Run a simple Triton benchmark with OpenAI-compatible chat inputs."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
import sys
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from runtimes.triton_runtime import TritonRuntime

DEFAULT_OUTPUT_DIR = Path("artifacts/triton")
DEFAULT_PROMPTS = [
    "Summarize dynamic batching for GPU inference.",
    "Explain why runtime abstraction is useful in evaluation platforms.",
    "How can Triton improve throughput for batched LLM workloads?",
    "Give one trade-off between latency and throughput.",
    "What metric should we monitor for inference stability?",
]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(round((pct / 100.0) * (len(sorted_values) - 1)))
    return sorted_values[index]


def run_triton_benchmark(
    prompts: list[str] | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    model_name: str | None = None,
) -> dict[str, Any]:
    runtime = TritonRuntime(model_name=model_name)
    active_prompts = prompts or DEFAULT_PROMPTS

    latency_results: list[dict[str, Any]] = []
    throughput_results: list[dict[str, Any]] = []

    for idx, prompt in enumerate(active_prompts, start=1):
        chat_request = {
            "model": model_name or runtime.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 128,
            "temperature": 0.0,
        }

        start = time.perf_counter()
        try:
            normalized = runtime.generate_chat(chat_request)
            status = "ok"
            output = normalized["output"]
            tokens_out = int(normalized["tokens_out"])
            latency_ms = float(normalized["latency_ms"])
        except Exception as exc:
            status = "error"
            output = f"mocked triton response for: {prompt}"
            tokens_out = max(4, len(output.split()))
            latency_ms = (time.perf_counter() - start) * 1000
            normalized = {
                "runtime": "triton",
                "model": model_name or runtime.model_name,
                "output": output,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
                "error": str(exc),
            }

        row = {
            "request_id": f"triton-bench-{idx:03d}",
            "prompt": prompt,
            "status": status,
            "latency_ms": round(latency_ms, 3),
            "tokens_out": tokens_out,
            "runtime": "triton",
        }
        latency_results.append(row)

        throughput_results.append(
            {
                "request_id": row["request_id"],
                "tokens_out": tokens_out,
                "latency_ms": row["latency_ms"],
                "tokens_per_sec": round(tokens_out / max(row["latency_ms"] / 1000.0, 1e-6), 3),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    latency_path = output_dir / "latency_results.json"
    throughput_path = output_dir / "throughput_results.json"
    summary_path = output_dir / "benchmark_summary.json"

    latency_path.write_text(json.dumps(latency_results, indent=2) + "\n", encoding="utf-8")
    throughput_path.write_text(json.dumps(throughput_results, indent=2) + "\n", encoding="utf-8")

    latencies = [float(row["latency_ms"]) for row in latency_results]
    tps_values = [float(row["tokens_per_sec"]) for row in throughput_results]
    success_count = sum(1 for row in latency_results if row["status"] == "ok")

    summary = {
        "runtime": "triton",
        "model": model_name or runtime.model_name,
        "total_requests": len(latency_results),
        "successful_requests": success_count,
        "error_requests": len(latency_results) - success_count,
        "p50_latency_ms": round(_percentile(latencies, 50), 3),
        "p95_latency_ms": round(_percentile(latencies, 95), 3),
        "avg_latency_ms": round(mean(latencies), 3) if latencies else 0.0,
        "avg_tokens_per_sec": round(mean(tps_values), 3) if tps_values else 0.0,
        "artifacts": {
            "latency_results": str(latency_path),
            "throughput_results": str(throughput_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    output_dir = Path(os.getenv("TRITON_BENCHMARK_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
    model_name = os.getenv("TRITON_BENCHMARK_MODEL")
    summary = run_triton_benchmark(output_dir=output_dir, model_name=model_name)
    print(json.dumps(summary, indent=2))
    print(f"Wrote Triton benchmark artifacts to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
