#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

try:
    from scripts.local_server import LocalServerManager
except ModuleNotFoundError:
    import sys
    from pathlib import Path as _Path

    sys.path.append(str(_Path(__file__).resolve().parent))
    from local_server import LocalServerManager

ARTIFACT_DIR = Path("artifacts")
SUMMARY_PATH = ARTIFACT_DIR / "gpu_benchmark_summary.json"


def _deterministic_latency_ms(quality_tier: str) -> float:
    normalized = quality_tier.strip().lower()
    if normalized == "fast":
        return 350.0
    if normalized == "high_quality":
        return 1200.0
    return 650.0


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int((pct / 100.0) * (len(ordered) - 1))
    return ordered[idx]


def _send_request(base_url: str, idx: int, quality_tier: str, use_mock_runtime: bool) -> dict:
    if use_mock_runtime:
        latency_ms = _deterministic_latency_ms(quality_tier)
        time.sleep(latency_ms / 1000.0)
        return {"ok": True, "latency_ms": latency_ms, "tokens": 40, "failure": ""}

    payload = {
        "messages": [{"role": "user", "content": f"ping {idx}"}],
        "latency_budget_ms": 1500,
        "quality_tier": quality_tier,
    }
    started = time.perf_counter()
    try:
        response = requests.post(f"{base_url}/v1/chat/completions", json=payload, timeout=30)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        total_tokens = int(body.get("usage", {}).get("total_tokens", 0))
        return {
            "ok": response.status_code == 200,
            "latency_ms": elapsed_ms,
            "tokens": total_tokens,
            "failure": "" if response.status_code == 200 else f"http_{response.status_code}",
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "tokens": 0,
            "failure": str(exc),
        }


def _write_summary(summary: dict) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def run_benchmark(
    base_url: str,
    requests_total: int,
    concurrency: int,
    quality_tier: str,
    spawn_server: bool,
    use_mock_runtime: bool,
) -> dict:
    manager = LocalServerManager(use_mock_runtime=use_mock_runtime)
    started_server = False

    try:
        server_ready = manager.wait_until_ready()
        if not server_ready and spawn_server:
            started_server = True
            server_ready = manager.start()

        if not server_ready and not use_mock_runtime:
            summary = {
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "tokens_per_second": 0.0,
                "requests_attempted": requests_total,
                "requests_succeeded": 0,
                "failure_reason": "server_unavailable",
            }
            _write_summary(summary)
            return summary

        workers = max(1, concurrency)
        results: list[dict] = []
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_send_request, base_url, i, quality_tier, use_mock_runtime)
                for i in range(requests_total)
            ]
            for future in as_completed(futures):
                results.append(future.result())
        elapsed_total_s = max(time.perf_counter() - started, 0.001)

        successes = [r for r in results if r["ok"]]
        latencies = [r["latency_ms"] for r in successes]
        total_tokens = sum(int(r["tokens"]) for r in successes)
        failure_reason = ""
        if not successes:
            failures = [r.get("failure", "") for r in results if not r["ok"]]
            failure_reason = failures[0] if failures else "all_requests_failed"

        summary = {
            "success_rate": round(len(successes) / max(requests_total, 1), 4),
            "avg_latency_ms": round((sum(latencies) / len(latencies)) if latencies else 0.0, 3),
            "p50_latency_ms": round(_percentile(latencies, 50), 3),
            "p95_latency_ms": round(_percentile(latencies, 95), 3),
            "tokens_per_second": round(total_tokens / elapsed_total_s, 3),
            "requests_attempted": requests_total,
            "requests_succeeded": len(successes),
            "failure_reason": failure_reason,
        }
        _write_summary(summary)
        return summary
    finally:
        if started_server:
            manager.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GPU benchmark harness")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--spawn-server", action="store_true")
    parser.add_argument("--use-mock-runtime", action="store_true")
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--quality-tier", default="balanced", choices=["fast", "balanced", "high_quality"])
    args = parser.parse_args()

    summary = run_benchmark(
        base_url=args.base_url,
        requests_total=max(1, args.requests),
        concurrency=max(1, args.concurrency),
        quality_tier=args.quality_tier,
        spawn_server=args.spawn_server,
        use_mock_runtime=args.use_mock_runtime,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
