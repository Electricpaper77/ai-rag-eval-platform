"""Bounded HTTP benchmark for baseline, degraded, and recovered Gate 7 traffic."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import urllib.parse
from collections import Counter
from pathlib import Path

import httpx


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, int(round((len(values) - 1) * percentile)))
    return values[index]


async def _run(args: argparse.Namespace) -> dict:
    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    latencies: list[float] = []
    workers: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    retry_counts: Counter[int] = Counter()
    started = time.perf_counter()

    async def send(client: httpx.AsyncClient, index: int) -> None:
        async with semaphore:
            request_id = f"{args.phase}-{index:04d}"
            payload = {"model": "mock", "messages": [{"role": "user", "content": f"Gate 7 request {index}"}], "request_id": request_id}
            request_started = time.perf_counter()
            try:
                response = await client.post(args.url, json=payload, headers={"x-request-id": request_id})
                latency_ms = (time.perf_counter() - request_started) * 1000
                latencies.append(latency_ms)
                if response.status_code != 200:
                    failures[str(response.status_code)] += 1
                    return
                body = response.json()
                routing = body.get("distributed_routing", {})
                worker_id = str(routing.get("selected_worker_id", "unknown"))
                workers[worker_id] += 1
                retry_counts[int(routing.get("retry_count", 0))] += 1
            except Exception as exc:
                failures[type(exc).__name__] += 1

    async with httpx.AsyncClient(timeout=args.timeout) as client:
        await asyncio.gather(*(send(client, index) for index in range(args.requests)))

    elapsed = max(time.perf_counter() - started, 1e-9)
    success_count = sum(workers.values())
    summary = {
        "phase": args.phase,
        "requests": args.requests,
        "successful_requests": success_count,
        "failed_requests": sum(failures.values()),
        "error_rate": round(sum(failures.values()) / max(args.requests, 1), 4),
        "throughput_requests_per_second": round(success_count / elapsed, 3),
        "p50_latency_ms": round(_percentile(latencies, 0.50), 3),
        "p95_latency_ms": round(_percentile(latencies, 0.95), 3),
        "per_worker_request_counts": dict(workers),
        "worker_utilization_ratio": round(min(workers.values()) / max(workers.values()), 4) if workers else 0.0,
        "failed_routes": dict(failures),
        "retry_counts": {str(key): value for key, value in sorted(retry_counts.items())},
        "elapsed_seconds": round(elapsed, 3),
    }
    if args.min_workers and len(workers) < args.min_workers:
        raise RuntimeError(f"expected at least {args.min_workers} workers, observed {sorted(workers)}")
    if args.require_success and failures:
        raise RuntimeError(f"benchmark failures: {dict(failures)}")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("DISTRIBUTION_SUMMARY " + json.dumps(summary, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--requests", type=int, required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", default="")
    parser.add_argument("--min-workers", type=int, default=0)
    parser.add_argument("--require-success", action="store_true")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
