from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from urllib import request


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = int((len(sorted_values) - 1) * p)
    return sorted_values[idx]


def post_chat_completion(base_url: str, model: str) -> tuple[float, int, bool]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a deterministic benchmark assistant."},
            {"role": "user", "content": "Return a short benchmarking response."},
        ],
        "max_tokens": 128,
        "temperature": 0.7,
    }

    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.perf_counter()
    try:
        with request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ok = 200 <= resp.status < 300
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return elapsed_ms, 0, False

    elapsed_ms = (time.perf_counter() - start) * 1000
    tokens = int(data.get("usage", {}).get("total_tokens", 0) or 0)
    return elapsed_ms, tokens, ok


def run(base_url: str, requests_total: int, model: str) -> dict:
    latencies: list[float] = []
    tokens_total = 0
    successes = 0

    start = time.perf_counter()
    for _ in range(requests_total):
        latency_ms, tokens, ok = post_chat_completion(base_url, model)
        latencies.append(latency_ms)
        tokens_total += tokens
        successes += int(ok)
    wall_seconds = max(time.perf_counter() - start, 1e-9)

    summary = {
        "requests": requests_total,
        "successes": successes,
        "success_rate": round(successes / requests_total, 4) if requests_total else 0.0,
        "p50_latency_ms": round(statistics.median(latencies) if latencies else 0.0, 3),
        "p95_latency_ms": round(percentile(latencies, 0.95), 3),
        "requests_per_sec": round(requests_total / wall_seconds, 3),
        "tokens_per_sec": round(tokens_total / wall_seconds, 3),
        "tokens_total": tokens_total,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local benchmark against /v1/chat/completions")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=25)
    parser.add_argument("--model", default="mock-llm")
    args = parser.parse_args()

    summary = run(args.base_url, args.requests, args.model)

    out_path = Path("artifacts/benchmark_summary.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"Saved benchmark summary -> {out_path}")


if __name__ == "__main__":
    main()
