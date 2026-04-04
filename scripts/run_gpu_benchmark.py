#!/usr/bin/env python3
"""Run GPU inference benchmark against an OpenAI-compatible chat completions endpoint."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from extract_token_metrics import extract_completion_tokens

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.2"
DEFAULT_NUM_REQUESTS = 5
DEFAULT_RUNTIME = "vllm"
DEFAULT_PROMPT = "Provide one concise sentence about GPU benchmarking."
OUTPUT_JSONL = Path("artifacts/proof/gpu_benchmark_run.jsonl")
OUTPUT_SUMMARY = Path("artifacts/proof/gpu_summary.json")


def percentile(sorted_values: list[float], pct: float) -> float:
    """Compute percentile using nearest-rank method for reproducible small samples."""

    if not sorted_values:
        return 0.0
    index = int(round((pct / 100) * (len(sorted_values) - 1)))
    return sorted_values[index]


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item) + "\n")


def write_summary(path: Path, runtime: str, successful_rows: list[dict[str, Any]]) -> None:
    latencies = sorted(float(row["latency_ms"]) for row in successful_rows)
    tps_values = [float(row["tokens_per_sec"]) for row in successful_rows]
    completion_values = [float(row["completion_tokens"]) for row in successful_rows]

    summary = {
        "runtime": runtime,
        "p50_latency_ms": round(percentile(latencies, 50), 2),
        "p95_latency_ms": round(percentile(latencies, 95), 2),
        "avg_tokens_per_sec": round(sum(tps_values) / len(tps_values), 2),
        "avg_completion_tokens": round(sum(completion_values) / len(completion_values), 2),
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def run_request(base_url: str, model_name: str, runtime: str, timeout_s: float = 60.0) -> dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": DEFAULT_PROMPT}],
        "max_tokens": 128,
        "temperature": 0.0,
    }

    started = time.perf_counter()
    try:
        response = requests.post(endpoint, json=payload, timeout=timeout_s)
        latency_ms = (time.perf_counter() - started) * 1000
        response.raise_for_status()

        body = response.json()
        usage = body.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = extract_completion_tokens(body)
        total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))

        latency_seconds = max(latency_ms / 1000, 1e-9)
        tokens_per_sec = completion_tokens / latency_seconds

        return {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "runtime": runtime,
            "model": model_name,
            "latency_ms": round(latency_ms, 2),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "tokens_per_sec": round(tokens_per_sec, 2),
            "requests_per_sec": round(1 / latency_seconds, 4),
            "status": "success",
        }
    except Exception as exc:  # benchmark should emit artifact even when endpoint fails
        latency_ms = (time.perf_counter() - started) * 1000
        return {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "runtime": runtime,
            "model": model_name,
            "latency_ms": round(latency_ms, 2),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "tokens_per_sec": 0.0,
            "requests_per_sec": 0.0,
            "status": "error",
            "error": str(exc),
        }


def main() -> int:
    base_url = os.getenv("BASE_URL", DEFAULT_BASE_URL)
    model_name = os.getenv("MODEL_NAME", DEFAULT_MODEL_NAME)
    runtime = os.getenv("RUNTIME", DEFAULT_RUNTIME)
    num_requests = int(os.getenv("NUM_REQUESTS", str(DEFAULT_NUM_REQUESTS)))

    rows: list[dict[str, Any]] = []
    for _ in range(num_requests):
        row = run_request(base_url=base_url, model_name=model_name, runtime=runtime)
        append_jsonl(OUTPUT_JSONL, row)
        rows.append(row)

    successful = [row for row in rows if row.get("status") == "success"]
    if successful:
        write_summary(OUTPUT_SUMMARY, runtime=runtime, successful_rows=successful)
    else:
        OUTPUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_SUMMARY.write_text(
            json.dumps(
                {
                    "runtime": runtime,
                    "p50_latency_ms": 0,
                    "p95_latency_ms": 0,
                    "avg_tokens_per_sec": 0,
                    "avg_completion_tokens": 0,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    print(f"Benchmark complete for {runtime}. Wrote {len(rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
