#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ARTIFACT_DIR = Path("artifacts")
SUMMARY_PATH = ARTIFACT_DIR / "gpu_benchmark_summary.json"


def _send_request(base_url: str, idx: int) -> dict:
    payload = {
        "messages": [{"role": "user", "content": f"ping {idx}"}],
        "latency_budget_ms": 1500,
        "quality_tier": "balanced",
    }
    started = time.perf_counter()
    try:
        response = requests.post(f"{base_url}/v1/chat/completions", json=payload, timeout=30)
        elapsed_ms = (time.perf_counter() - started) * 1000
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        total_tokens = int(body.get("usage", {}).get("total_tokens", 0))
        return {
            "ok": response.status_code == 200,
            "latency_ms": elapsed_ms,
            "tokens": total_tokens,
        }
    except requests.RequestException:
        return {"ok": False, "latency_ms": (time.perf_counter() - started) * 1000, "tokens": 0}


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int((pct / 100) * (len(ordered) - 1))
    return ordered[idx]


def main() -> int:
    base_url = "http://localhost:8000"
    n_requests = 50
    workers = 50
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_send_request, base_url, i) for i in range(n_requests)]
        for future in as_completed(futures):
            results.append(future.result())

    successes = [r for r in results if r["ok"]]
    latencies = [r["latency_ms"] for r in successes]
    elapsed_total_s = max(sum(r["latency_ms"] for r in results) / 1000.0, 0.001)
    summary = {
        "total_requests": n_requests,
        "parallelism": workers,
        "success_count": len(successes),
        "success_rate": round(len(successes) / n_requests, 4),
        "p50_latency_ms": round(_percentile(latencies, 50), 3),
        "p95_latency_ms": round(_percentile(latencies, 95), 3),
        "tokens_generated_total": int(sum(r["tokens"] for r in successes)),
        "aggregate_tokens_per_second": round(sum(r["tokens"] for r in successes) / elapsed_total_s, 3),
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
