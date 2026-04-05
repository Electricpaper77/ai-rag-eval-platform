#!/usr/bin/env python3
"""Run a real sequential vLLM OpenAI-compatible benchmark and persist summary artifact."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_MODEL = "mistral-7b"
DEFAULT_REQUESTS = 50
DEFAULT_RUNTIME = "vllm"
DEFAULT_ARTIFACT = Path("artifacts/benchmarks/gpu_real_run.json")

PAYLOAD_TEMPLATE = {
    "model": DEFAULT_MODEL,
    "messages": [
        {"role": "system", "content": "benchmark"},
        {"role": "user", "content": "Explain vector databases in 2 sentences"},
    ],
    "max_tokens": 120,
}


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = round((len(values) - 1) * (pct / 100.0))
    return values[int(idx)]


def completion_tokens_from_response(body: dict[str, Any]) -> int:
    usage = body.get("usage", {}) if isinstance(body, dict) else {}
    completion_tokens = usage.get("completion_tokens")
    if completion_tokens is not None:
        return int(completion_tokens)

    choices = body.get("choices", []) if isinstance(body, dict) else []
    if not choices:
        return 0
    content = str(choices[0].get("message", {}).get("content", ""))
    return max(len(content.split()), 1)


def run_benchmark(base_url: str, model: str, request_count: int, timeout_s: float) -> dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload = dict(PAYLOAD_TEMPLATE)
    payload["model"] = model

    latencies_ms: list[float] = []
    completion_tokens = 0
    failures: list[dict[str, Any]] = []
    failed_requests = 0
    max_logged_errors = 5

    started = time.perf_counter()

    for idx in range(request_count):
        request_started = time.perf_counter()
        try:
            response = requests.post(endpoint, json=payload, timeout=timeout_s)
            latency_ms = (time.perf_counter() - request_started) * 1000
            response.raise_for_status()

            body = response.json()
            latencies_ms.append(latency_ms)
            completion_tokens += completion_tokens_from_response(body)
        except Exception as exc:
            failed_requests += 1
            if len(failures) < max_logged_errors:
                failures.append({"request_index": idx, "error": str(exc)})

    total_time_sec = max(time.perf_counter() - started, 1e-9)
    successful_requests = len(latencies_ms)

    summary: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": DEFAULT_RUNTIME,
        "model": model,
        "requests": request_count,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "total_time_sec": round(total_time_sec, 4),
        "requests_per_sec": round(successful_requests / total_time_sec, 4),
        "avg_latency_ms": round(sum(latencies_ms) / successful_requests, 2) if successful_requests else 0.0,
        "p95_latency_ms": round(percentile(latencies_ms, 95), 2) if successful_requests else 0.0,
        "tokens_per_second": round(completion_tokens / total_time_sec, 4),
        "endpoint": endpoint,
    }

    if failures:
        summary["errors"] = failures
        summary["errors_truncated"] = max(failed_requests - len(failures), 0)

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--requests", type=int, default=DEFAULT_REQUESTS)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_ARTIFACT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run_benchmark(
        base_url=args.base_url,
        model=args.model,
        request_count=args.requests,
        timeout_s=args.timeout,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

    return 0 if summary["successful_requests"] == summary["requests"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
