#!/usr/bin/env python3
"""Run vendor-agnostic benchmark through /platform/route and emit JSONL artifacts."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

OUTPUT = Path("artifacts/proof/benchmark_runs.jsonl")


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = int((pct / 100) * (len(values) - 1))
    return values[idx]


def main() -> int:
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    requests_n = int(os.getenv("NUM_REQUESTS", "10"))
    quality_tier = os.getenv("QUALITY_TIER", "balanced")
    latency_budget_ms = int(os.getenv("LATENCY_BUDGET_MS", "1500"))

    rows: list[dict] = []
    for i in range(requests_n):
        payload = {
            "prompt": f"Benchmark request {i}: summarize gpu control plane.",
            "quality_tier": quality_tier,
            "latency_budget_ms": latency_budget_ms,
            "max_tokens": 128,
            "queue_if_busy": True,
        }
        start = time.perf_counter()
        try:
            r = requests.post(f"{base_url.rstrip('/')}/platform/route", json=payload, timeout=30)
            elapsed_ms = (time.perf_counter() - start) * 1000
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            row = {
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "request_id": i,
                "http_status": r.status_code,
                "runtime": body.get("runtime"),
                "status": body.get("status", "error"),
                "latency_ms": round(float(body.get("latency_ms", elapsed_ms)), 2),
                "tokens_per_sec": float(body.get("tokens_per_sec", 0.0)),
                "autoscale_action": body.get("autoscaling", {}).get("action"),
            }
        except requests.RequestException as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            row = {
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "request_id": i,
                "http_status": 0,
                "runtime": None,
                "status": "error",
                "latency_ms": round(elapsed_ms, 2),
                "tokens_per_sec": 0.0,
                "autoscale_action": None,
                "error": str(exc),
            }
        append_jsonl(OUTPUT, row)
        rows.append(row)

    success = [r for r in rows if r["status"] == "ok"]
    summary = {
        "requests": requests_n,
        "success_rate": round(len(success) / max(len(rows), 1), 3),
        "p50_latency_ms": round(percentile([r["latency_ms"] for r in success], 50), 2),
        "p95_latency_ms": round(percentile([r["latency_ms"] for r in success], 95), 2),
        "avg_tokens_per_sec": round(sum(r["tokens_per_sec"] for r in success) / max(len(success), 1), 2),
        "artifact": str(OUTPUT),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
