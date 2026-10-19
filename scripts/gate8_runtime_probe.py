"""Bounded live probe for Gate 8 healthy and degraded canary phases."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter

import httpx


def call(client: httpx.Client, base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    post_paths = {"/serving/chat", "/canary/start", "/canary/promote", "/canary/rollback"}
    response = client.post(base_url + path, json=payload or {}) if payload is not None or path in post_paths else client.get(base_url + path)
    try:
        body = response.json()
    except ValueError:
        body = {"text": response.text}
    return response.status_code, body


def traffic(client: httpx.Client, base_url: str, phase: str, count: int, allow_errors: bool = False) -> dict:
    workers = Counter()
    statuses = Counter()
    latencies: list[float] = []
    for index in range(count):
        request_id = f"{phase}-{index:04d}"
        started = time.perf_counter()
        status, body = call(client, base_url, "/serving/chat", {"model": "mock-llm", "messages": [{"role": "user", "content": request_id}], "request_id": request_id})
        latencies.append((time.perf_counter() - started) * 1000.0)
        statuses[str(status)] += 1
        if status == 200:
            workers[str(body.get("serving", {}).get("model_version", "unknown"))] += 1
        elif not allow_errors:
            raise RuntimeError(f"{phase} request {request_id} failed: HTTP {status} {body}")
    return {
        "phase": phase,
        "requests": count,
        "statuses": dict(statuses),
        "successful_requests": sum(workers.values()),
        "per_version_requests": dict(workers),
        "p50_latency_ms": round(statistics.median(latencies), 3),
        "p95_latency_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 3),
    }


def healthy(base_url: str) -> dict:
    with httpx.Client(timeout=20.0) as client:
        router_root = base_url.removesuffix("/platform")
        status, body = call(client, router_root, "/healthz")
        if status != 200:
            raise RuntimeError(f"router health failed: {status} {body}")
        status, body = call(client, base_url, "/serving/status")
        if status != 200:
            raise RuntimeError(f"serving status failed: {status} {body}")
        baseline = traffic(client, base_url, "baseline", 100)
        started, state = call(client, base_url, "/canary/start")
        if started != 200 or state.get("phase") != "CANARY":
            raise RuntimeError(f"canary start failed: {started} {state}")
        stage1 = traffic(client, base_url, "healthy-stage1", 100)
        promoted_stage = call(client, base_url, "/canary/promote")[1]
        stage2 = traffic(client, base_url, "healthy-stage2", 100)
        promoted = call(client, base_url, "/canary/promote")[1]
        if promoted.get("phase") != "PROMOTED":
            raise RuntimeError(f"healthy candidate did not promote: {promoted}")
        return {"baseline": baseline, "stage1": stage1, "stage2": stage2, "promoted": promoted}


def degraded(base_url: str) -> dict:
    with httpx.Client(timeout=20.0) as client:
        rollback = call(client, base_url, "/canary/rollback")[1]
        if rollback.get("weights", {}).get("baseline") != 100:
            raise RuntimeError(f"reset rollback failed: {rollback}")
        started, state = call(client, base_url, "/canary/start")
        if started != 200:
            raise RuntimeError(f"degraded canary start failed: {started} {state}")
        traffic_result = traffic(client, base_url, "degraded-stage1", 100, allow_errors=True)
        promoted = call(client, base_url, "/canary/promote")[1]
        if promoted.get("phase") != "ROLLED_BACK":
            raise RuntimeError(f"degraded candidate was not rolled back: {promoted}")
        status, body = call(client, base_url, "/serving/chat", {"model": "mock-llm", "messages": [{"role": "user", "content": "post rollback"}], "request_id": "post-rollback"})
        if status != 200 or body.get("serving", {}).get("model_version") != "baseline":
            raise RuntimeError(f"baseline did not serve after rollback: {status} {body}")
        return {"traffic": traffic_result, "rollback": promoted, "post_rollback": body}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--phase", choices=("healthy", "degraded"), required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = healthy(args.base_url) if args.phase == "healthy" else degraded(args.base_url)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
